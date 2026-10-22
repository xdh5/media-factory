"""OpenAI 兼容网关、人工审批、视频预览与诊断管理入口。"""

from contextlib import asynccontextmanager
import asyncio
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import uuid

from dotenv import dotenv_values
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse

from agent.diagnostics.knowledge import KnowledgeBase
from agent.diagnostics.redaction import redact
from agent.diagnostics.tracing import TraceStore
from agent.journal import CallJournal
from agent.settings import ROOT, SERVERS, llm_configuration
from .runtime import AgentRuntime

HOME = Path(os.getenv("MEDIA_FACTORY_HOME", ROOT / "data/desktop")).resolve()
HOME.mkdir(parents=True, exist_ok=True)
DATABASE = Path(os.getenv("MEDIA_FACTORY_AGENT_DATABASE", HOME / "agent.sqlite")).resolve()
DATABASE.parent.mkdir(parents=True, exist_ok=True)
TOKEN = os.getenv("MEDIA_FACTORY_SESSION_TOKEN") or secrets.token_hex(32)
os.environ["MEDIA_FACTORY_SESSION_TOKEN"] = TOKEN
if not os.getenv("MEDIA_FACTORY_AGENT_PORT"):
    (HOME / "session.token").write_text(TOKEN, encoding="utf-8")
WORKSPACE = Path(os.getenv("MEDIA_FACTORY_WORKSPACE", ROOT)).resolve()
MEDIA_KEY_FILE = HOME / "media-signing.key"
if not MEDIA_KEY_FILE.exists():
    MEDIA_KEY_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
MEDIA_KEY = MEDIA_KEY_FILE.read_text(encoding="utf-8")
runtime = AgentRuntime(DATABASE)


@asynccontextmanager
async def lifespan(app):
    runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(title="Media Factory 本地 Agent", lifespan=lifespan)


@app.exception_handler(ValueError)
async def invalid_request(request, error):
    return JSONResponse({"detail": redact(str(error))}, status_code=400)


def authenticated(request: Request):
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ") or request.cookies.get("media_factory_session", "")
    if not secrets.compare_digest(supplied, TOKEN):
        raise HTTPException(401, "需要本地客户端授权")


@app.get("/health")
async def health():
    if runtime.worker and runtime.worker.done():
        raise HTTPException(503, "MCP 服务不可用，请查看脱敏日志")
    return {"status": "ok"}


@app.get("/console", response_class=HTMLResponse)
async def console(request: Request):
    token = request.query_params.get("token")
    if token:
        if not secrets.compare_digest(token, TOKEN):
            raise HTTPException(401)
        response = RedirectResponse("/console", status_code=303)
        response.set_cookie("media_factory_session", TOKEN, httponly=True, samesite="strict")
        return response
    authenticated(request)
    return HTMLResponse((Path(__file__).parent / "console.html").read_text(encoding="utf-8"))


@app.get("/v1/models", dependencies=[Depends(authenticated)])
async def models():
    model = llm_configuration()["model"]
    return {"object": "list", "data": [{"id": model, "name": model,
            "object": "model", "created": 0, "owned_by": "media-factory"}]}


def media_links(result, request):
    content = json.dumps(result, ensure_ascii=False)
    import re
    paths = re.findall(r'"([^"\n]+\.(?:mp4|webm|mov))"', content, re.IGNORECASE)
    links = []
    for raw in paths:
        path = Path(raw.replace("\\\\", "\\")).resolve()
        if path.is_file() and path.is_relative_to(WORKSPACE / "cache"):
            encoded = base64.urlsafe_b64encode(str(path).encode()).decode().rstrip("=")
            signature = hmac.new(MEDIA_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
            url = str(request.base_url).rstrip("/") + f"/media/{encoded}?signature={signature}"
            links.append(f"\n[预览视频：{path.name}]({url})\n")
    return list(dict.fromkeys(links))


def result_text(result, request):
    lines = []
    for pending in result.get("interrupts", []):
        identity = pending["id"]
        if pending["kind"] == "approval":
            lines.append("\n这一步需要你确认，我还没有执行。\n")
            lines.append("操作：`" + pending.get("tool", "敏感操作") + "`\n")
            lines.append("```json\n" + json.dumps(redact(pending.get("arguments", {})), ensure_ascii=False, indent=2) + "\n```\n")
            lines.append("直接在当前对话回复“同意”或“取消”即可。\n")
        elif pending["kind"] == "pause":
            lines.append("\n任务已暂停，直接回复“继续”即可。\n")
        elif pending["kind"] == "uncertain":
            lines.append("\n上次操作的结果尚未确认，我已停止自动重试，避免重复执行。请先核对实际业务结果。\n")
        elif pending["kind"] == "input":
            lines.append("\n" + str(pending.get("question", pending.get("message", "请补充任务所需的信息。"))) + "\n")
    if result.get("status") == "recoverable":
        lines.append("\n任务可恢复，发送 `/恢复` 继续。\n")
    if result.get("status") == "limit_reached":
        lines.append("\n本轮已达到执行次数上限，进度已保存。在当前聊天回复“继续”即可接着执行，无需新建聊天。\n")
    lines.extend(media_links(result, request))
    return "".join(lines)


@app.post("/v1/chat/completions", dependencies=[Depends(authenticated)])
async def chat(request: Request):
    body = await request.json()
    model = body.get("model", "")
    # 已有聊天保留原任务映射，新聊天使用真实模型标识。
    if model.startswith("media-factory-") and model.removeprefix("media-factory-") in SERVERS:
        model = model.removeprefix("media-factory-")
    elif model != llm_configuration()["model"]:
        raise HTTPException(400, "请选择已配置的模型")
    chat_id = request.headers.get("x-openwebui-chat-id") or body.get("metadata", {}).get("chat_id")
    if not chat_id:
        raise HTTPException(400, "需要 X-OpenWebUI-Chat-Id 或 metadata.chat_id 维持检查点")
    user_id = request.headers.get("x-openwebui-user-id", "local")
    task_id = "chat-" + hashlib.sha256(f"{user_id}:{chat_id}:{model}".encode()).hexdigest()
    message = next((item["content"] for item in reversed(body.get("messages", [])) if item["role"] == "user"), "")
    if not isinstance(message, str):
        raise HTTPException(400, "当前 Agent 只接收文本任务，视频通过工具产物预览")
    response, interrupt_id = None, None
    parts = message.strip().split(maxsplit=1)
    if parts and parts[0] in {"/批准", "/拒绝", "/继续"}:
        if len(parts) != 2:
            raise HTTPException(400, "操作必须带当前中断 ID")
        interrupt_id = parts[1]
        response = {} if parts[0] == "/继续" else {"approved": parts[0] == "/批准"}
    try:
        events = await runtime.submit(task_id, model, "" if message == "/恢复" else message, response, interrupt_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    identity = "chatcmpl-" + uuid.uuid4().hex
    async def fragments():
        has_tokens = False
        last_progress = {}
        while True:
            event = await events.get()
            if event["kind"] == "done":
                break
            if event["kind"] == "token":
                has_tokens = True
                yield event["text"]
            elif event["kind"] == "tool":
                if event["name"] == "agent_load_tools":
                    continue
                if event["name"].endswith("_poll_task"):
                    payload = event.get("payload", {})
                    result = payload.get("result", {})
                    if isinstance(result, dict) and result.get("done") is False and event["status"] == "ok":
                        task = json.dumps(payload.get("arguments", {}), sort_keys=True)
                        progress = result.get("progress") or "任务执行中，正在等待处理结果。"
                        if last_progress.get(task) != progress:
                            last_progress[task] = progress
                            yield f"\n\n> {progress}\n\n"
                        continue
                yield f"\n\n> 工具 `{event['name']}`：{event['status']}\n\n"
                paths = media_links(event.get("artifacts", []), request)
                for link in paths:
                    yield link
            elif event["kind"] == "result":
                if not has_tokens and event.get("last_message", {}).get("role") == "assistant":
                    yield event["last_message"].get("content") or ""
                yield result_text(event, request)
            elif event["kind"] == "error":
                yield "\n执行失败：" + redact(event["error"]) + f"\n任务 `{task_id}` 的检查点已保留。"
    if not body.get("stream", False):
        content = "".join([text async for text in fragments()])
        return {"id": identity, "object": "chat.completion", "created": int(time.time()), "model": body["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    async def stream():
        async for text in fragments():
            chunk = {"id": identity, "object": "chat.completion.chunk", "created": int(time.time()), "model": body["model"],
                     "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"id": identity, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/media/{encoded}")
async def media(encoded: str, signature: str):
    expected = hmac.new(MEDIA_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403)
    path = Path(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()).resolve()
    if not path.is_relative_to(WORKSPACE / "cache") or path.suffix.lower() not in {".mp4", ".webm", ".mov"} or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/overview", dependencies=[Depends(authenticated)])
async def overview():
    return {"runs": runtime.store.list_runs(), "documents": KnowledgeBase(DATABASE).list_documents(),
            "evaluations": runtime.store.evaluations(), "configuration": list(dotenv_values(HOME / "config.env")),
            "home": str(HOME)}


@app.get("/api/traces/{run_id}", dependencies=[Depends(authenticated)])
async def traces(run_id: str):
    return runtime.store.chain(run_id)


@app.get("/api/tasks/{task_id}", dependencies=[Depends(authenticated)])
async def task_status(task_id: str):
    result = runtime.output(await runtime.snapshot(task_id))
    if task_id in runtime.active and not result["interrupts"]:
        result["status"] = "running"
    return redact(result)


@app.post("/api/tasks/{task_id}/pause", dependencies=[Depends(authenticated)])
async def pause(task_id: str):
    journal = CallJournal(DATABASE)
    journal.pause(task_id)
    journal.close()
    return {"status": "pause_requested"}


@app.post("/api/tasks/{task_id}/resume", dependencies=[Depends(authenticated)])
async def resume(task_id: str, request: Request):
    body = await request.json()
    snapshot = await runtime.snapshot(task_id)
    if not snapshot.values:
        raise HTTPException(404)
    await runtime.submit(task_id, snapshot.values["servers"][0], response=body.get("response"), interrupt_id=body.get("interrupt_id"))
    return {"status": "queued"}


@app.post("/api/config", dependencies=[Depends(authenticated)])
async def configure(request: Request):
    body = await request.json()
    raw = body["environment"]
    import io, re
    configuration = dotenv_values(stream=io.StringIO(raw))
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in configuration):
        raise HTTPException(400, "环境配置变量名称无效")
    forbidden = {"PATH", "PYTHONPATH", "PYTHONHOME", "MEDIA_FACTORY_SESSION_TOKEN", "MEDIA_FACTORY_HOME", "MEDIA_FACTORY_WORKSPACE", "MEDIA_FACTORY_AGENT_DATABASE"}
    if forbidden.intersection(configuration):
        raise HTTPException(400, "不能覆盖客户端运行目录或会话授权")
    (HOME / "config.env").write_text(raw, encoding="utf-8")
    os.environ.update({key: value for key, value in configuration.items() if value is not None})
    return {"saved": True, "message": "模型配置已生效；MCP 业务配置变更后请重启客户端"}


@app.post("/api/knowledge/search", dependencies=[Depends(authenticated)])
async def search(request: Request):
    body = await request.json()
    return await KnowledgeBase(DATABASE).search(body["query"], k=min(20, max(1, body.get("k", 5))))


@app.post("/api/knowledge/ingest", dependencies=[Depends(authenticated)])
async def ingest(request: Request):
    body = await request.json()
    if body.get("kind") == "solution" and body.get("verified") is not True:
        raise HTTPException(400, "解决方案必须经人工核验")
    identity = await KnowledgeBase(DATABASE).ingest(body["source"], body["content"], body.get("kind", "document"), body.get("evidence", ""))
    return {"id": identity}


@app.post("/api/knowledge/import-project", dependencies=[Depends(authenticated)])
async def import_project():
    knowledge = KnowledgeBase(DATABASE)
    documents = []
    paths = list((WORKSPACE / "docs").rglob("*.md")) + list((WORKSPACE / "agent").glob("*.md"))
    for path in paths:
        documents.append(await knowledge.ingest(str(path.relative_to(WORKSPACE)), path.read_text(encoding="utf-8")))
    return {"imported": len(documents)}


@app.post("/api/knowledge/reindex", dependencies=[Depends(authenticated)])
async def reindex():
    return await KnowledgeBase(DATABASE).reindex()


@app.post("/api/runs/{run_id}/label", dependencies=[Depends(authenticated)])
async def label(run_id: str, request: Request):
    body = await request.json()
    if type(body.get("success")) is not bool:
        raise HTTPException(400)
    runtime.store.label(run_id, body["success"], body["evidence"])
    return {"saved": True}


@app.post("/api/evals/{kind}", dependencies=[Depends(authenticated)])
async def evaluate(kind: str, request: Request):
    from agent.diagnostics.evaluation import agent_metrics, evaluate_rag
    body = await request.json()
    if kind == "agent":
        report = agent_metrics(runtime.store)
    elif kind == "rag":
        report = await evaluate_rag(KnowledgeBase(DATABASE), body["cases"], body.get("k", 5))
    else:
        raise HTTPException(404)
    runtime.store.save_evaluation(kind, report)
    return report


@app.post("/api/evals/{evaluation_id}/diagnosis-label", dependencies=[Depends(authenticated)])
async def diagnosis_label(evaluation_id: str, request: Request):
    body = await request.json()
    return runtime.store.label_diagnosis(evaluation_id, body["case_id"], body["correct"], body["evidence"])


@app.post("/api/shutdown", dependencies=[Depends(authenticated)])
async def shutdown():
    (HOME / "shutdown.request").touch()
    return {"stopping": True}
