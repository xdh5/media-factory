"""通过真实 HTTP、LLM 和 stdio MCP 验证桌面接入，不执行发布。"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx
from agent.diagnostics.redaction import redact


def main():
    from desktop.supervisor import windows_job
    process_job = windows_job()
    home = ROOT / "cache/desktop-verification" / uuid.uuid4().hex
    home.mkdir(parents=True)
    token = uuid.uuid4().hex
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {**os.environ, "MEDIA_FACTORY_HOME": str(home), "MEDIA_FACTORY_SESSION_TOKEN": token,
                   "DASHSCOPE_BUSINESS_LINE": "finance", "PYTHONUTF8": "1"}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "desktop.gateway:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report = {"database": str(home / "agent.sqlite"), "backend_pid": process.pid, "checks": []}
    base = f"http://127.0.0.1:{port}"
    headers = {"Authorization": "Bearer " + token, "X-OpenWebUI-Chat-Id": "real-integration-chat"}
    def checked(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)
        print(name, flush=True)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/health", timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        with httpx.Client(base_url=base, headers=headers, timeout=180) as client:
            checked("未授权请求被拒绝", httpx.get(base + "/api/overview").status_code == 401)
            checked("真实千问模型可发现", [item["id"] for item in client.get("/v1/models").json()["data"]] == ["qwen-plus"])
            body = {"model": "qwen-plus", "stream": True,
                    "messages": [{"role": "user", "content": "只调用一次 finance_get_production_config，然后用一句中文概括素材方案。不要生产、写库或发布。"}]}
            parts = []
            with client.stream("POST", "/v1/chat/completions", json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        parts.append(chunk["choices"][0]["delta"].get("content", ""))
            checked("真实模型 SSE 流式工具调用", len(parts) > 2 and "finance_get_production_config" in "".join(parts))
            runs = client.get("/api/overview").json()["runs"]
            task_id = runs[0]["task_id"]
            state = client.get("/api/tasks/" + task_id).json()
            checked("首轮检查点完成", state["status"] == "completed")
            async def reach_execution_limit():
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                from langgraph.graph import START
                from agent.workflow import build_graph
                from agent.settings import AgentSettings
                async with AsyncSqliteSaver.from_conn_string(str(home / "agent.sqlite")) as saver:
                    graph = build_graph(None, None, None, saver, AgentSettings(), task_id)
                    config = {"configurable": {"thread_id": task_id}}
                    snapshot = await graph.aget_state(config)
                    await graph.aupdate_state(config, {"status": "limit_reached", "max_steps": snapshot.values["steps"]}, as_node=START)
            asyncio.run(reach_execution_limit())
            continued = client.post("/v1/chat/completions", json={"model": "qwen-plus", "stream": False,
                "messages": [{"role": "user", "content": "继续。只概括刚才查询到的配置，不要调用工具。"}]})
            continued.raise_for_status()
            checked("达到执行上限后原聊天可恢复", client.get("/api/tasks/" + task_id).json()["status"] == "completed")
            chain = client.get("/api/traces/" + runs[0]["id"]).json()
            checked("链路包含 LLM、工具与执行节点", {"llm", "tool", "node"}.issubset({span["kind"] for span in chain}))
            checked("真实 Token 用量被记录", any(span["prompt_tokens"] for span in chain if span["kind"] == "llm"))
            second = client.post("/v1/chat/completions", json={"model": "qwen-plus", "stream": False,
                "messages": [{"role": "user", "content": "上一轮查询的素材方案是什么？不要再次调用工具，只根据记忆用一句话回答。"}]}).json()
            checked("多轮会话可继续", bool(second["choices"][0]["message"]["content"]))
            automatic_headers = {**headers, "X-OpenWebUI-Chat-Id": "automatic-tool-integration-chat"}
            response = client.post("/v1/chat/completions", headers=automatic_headers, json={"model": "qwen-plus", "stream": False,
                "messages": [{"role": "user", "content": "只调用一次 finance_get_topics 查询已占用话题，回复话题条数。不要写库、生产或发布。"}]})
            response.raise_for_status()
            run = client.get("/api/overview").json()["runs"][0]
            state = client.get("/api/tasks/" + run["task_id"]).json()
            checked("原需审批工具直接执行且无人工中断", state["status"] == "completed" and not state["interrupts"])
            spans = client.get("/api/traces/" + run["id"]).json()
            checked("真实查询工具已执行", any(span["kind"] == "tool" and span["name"] == "finance_get_topics" and span["status"] == "ok" for span in spans))
            first_run = runs[0]["id"]
            client.post("/api/runs/" + first_run + "/label", json={"success": True,
                "evidence": "本次真实模型只读配置查询返回有效配置，SSE 完成，SQLite 工具回执和链路齐全。"}).raise_for_status()
            metrics = client.post("/api/evals/agent", json={}).json()
            checked("Agent 指标基于真实集成验收标签", metrics["labeled_task_count"] == 1 and metrics["task_success_rate"] == 1)
            report["agent_metrics"] = metrics
            checked("未知查询参数中的凭据会脱敏", "sensitive-example" not in redact("https://a.test?TrustedClientToken=sensitive-example&Sec-MS-GEC=private"))
            video = home / "preview.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
            encoded = base64.urlsafe_b64encode(str(video.resolve()).encode()).decode().rstrip("=")
            signing_key = (home / "media-signing.key").read_text(encoding="utf-8")
            signature = hmac.new(signing_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
            url = f"/media/{encoded}?signature={signature}"
            checked("视频支持 Range 预览", client.get(url, headers={"Range": "bytes=0-127"}).status_code == 206)
            checked("无效视频签名被拒绝", client.get(f"/media/{encoded}?signature=invalid").status_code == 403)
            process.terminate()
            process.wait(timeout=15)
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "desktop.gateway:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                try:
                    urllib.request.urlopen(base + "/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.5)
            checked("后端重启后检查点保留", client.get("/api/tasks/" + task_id).json()["status"] == "completed")
            checked("后端重启后视频签名仍有效", client.get(url).status_code == 200)
        report["status"] = "passed"
    finally:
        process.terminate()
        process.wait(timeout=15)
        path = home / "verification.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("验收记录：" + str(path), flush=True)


if __name__ == "__main__":
    main()
