"""财经生产阶段实现与完整编排。"""
from __future__ import annotations
import asyncio
import json
import re
from datetime import date as calendar_date
from filelock import FileLock
from pathlib import Path
from .tools import drafts as a, assemble_finance_video as d
from workflows.finance.parameters import MATERIAL_STOCK_VIDEO, normalize_publish_date, production_dirs
from workflows.finance.errors.exceptions import WorkflowStepError
from tools.task_runner import submit_task as runner_submit_task
from workflows.finance.tools.storyboard import prepare_storyboard, parse_storyboard
from workflows.finance.tools.assemble_finance_video import upload_finance_assets_to_r2
from tools.task_runner import poll_task
from workflows.finance.tools.storyboard_images import restore_storyboard_images, bind_storyboard_images

def finance_get_config():
    return a.finance_get_production_config()


def _state_path(workflow_id: str) -> Path:
    match = re.fullmatch(r"finance-(\d{8})-part([1-9]\d*)", workflow_id)
    if match is None:
        raise WorkflowStepError("workflow_id 格式必须为 finance-YYYYMMDD-partN")
    cache_root, _ = production_dirs(f"run-{match[1]}", int(match[2]))
    return cache_root / "production-workflow.json"


def _read_state(workflow_id: str) -> dict:
    return json.loads(_state_path(workflow_id).read_text(encoding="utf-8"))


def _submit_preparation(state_path: Path, state: dict) -> dict:
    config = finance_get_config()
    def work():
        current = json.loads(state_path.read_text(encoding="utf-8"))
        result = prepare_storyboard(current["draft_path"], tts_config=config["tts_config"], material_strategy=MATERIAL_STOCK_VIDEO)
        draft = json.loads(Path(current["draft_path"]).read_text(encoding="utf-8"))
        image_root = state_path.parent / "generated-images"
        image_root.mkdir(parents=True, exist_ok=True)
        restored = restore_storyboard_images(draft["source_aweme_id"], draft["storyboard"], image_root)
        if restored:
            bind_storyboard_images(draft)
        shot_count = len([row for row in draft["storyboard"].splitlines() if row.strip()]) - 1
        needs_images = current["generate_images"] and not {f"shot-{i:03d}" for i in range(1, shot_count + 1)}.issubset(restored)
        current["stage"] = "awaiting_images" if needs_images else "ready_to_search"
        if needs_images:
            result["image_requests"] = [
                {"id": shot["id"], "narration": shot["subtitle"], "description": shot["description"],
                 "output_path": str(image_root / f"{shot['id']}.png")}
                for shot in parse_storyboard(result["storyboard_text"], result["timeline"])[:-1]
            ]
        current["storyboard_context"] = {key: value for key, value in result.items()
                                         if key not in {"draft_path", "context_path"}}
        _save_state(state_path, current)
        return {**current["storyboard_context"], "workflow_id": current["workflow_id"],
                "stage": current["stage"], "next_tool": "finance_continue_production"}
    task = runner_submit_task(cache_dir=state_path.parent, run_id=state["run_id"], step="prepare_production", fn=work)
    _save_state(state_path.with_name("production-task.json"), {"task_path": task["task_path"]})
    return {"workflow_id": state["workflow_id"], "status": task["status"], "generate_images": state["generate_images"]}


def finance_start_production(publish_date: str, content_part: int = 1, *, generate_images: bool = False) -> dict:
    """按日期和分片启动或恢复同一生产流程，只返回 workflow_id。"""
    date = calendar_date.fromisoformat(publish_date).isoformat()
    if content_part < 1:
        raise WorkflowStepError("内容分片必须为正整数")
    workflow_id = f"finance-{date.replace('-', '')}-part{content_part}"
    state_path = _state_path(workflow_id)
    if not state_path.exists():
        normalize_publish_date(date)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(state_path.with_suffix(".lock")):
        if state_path.exists():
            state = _read_state(workflow_id)
            if "draft_path" in state:
                if state["stage"] == "preparing":
                    return _submit_preparation(state_path, state)
                return {"workflow_id": workflow_id, "stage": state["stage"], "generate_images": state["generate_images"]}
        else:
            state = {"workflow_id": workflow_id, "run_id": f"run-{date.replace('-', '')}",
                     "publish_date": date, "content_part": content_part, "stage": "reserving",
                     "generate_images": generate_images}
            _save_state(state_path, state)
        if "source" not in state:
            selected = a.finance_get_source_script()
            state.update({"source": selected["source"], "reservation": selected["reservation"]})
            _save_state(state_path, state)
        source, reservation = state["source"], state["reservation"]
        editorial = next(row["editorial"] for row in a.list_editorial_drafts(False)["records"]
                         if row["aweme_id"] == source["aweme_id"])
        if editorial.get("storyboard_status") == "pending":
            raise WorkflowStepError("正文已更新，分镜待同步，暂不能生产")
        cover_images = editorial.get("cover_images", {})
        if set(cover_images) != {"landscape", "portrait"} or any(
                (asset["title"], asset["short_title"]) != (editorial["title"], editorial["short_title"])
                for asset in cover_images.values()):
            raise WorkflowStepError("稿件缺少与当前标题一致的横竖双封面成图，请由宿主完成封面生图并登记")
        draft = a.finance_save_draft(
            **{key: editorial[key] for key in ("topic", "article", "storyboard", "title", "short_title", "hashtags",
               "cover_lines", "cover_highlights", "source_hook", "db_source_hook")},
            source_aweme_id=str(source["aweme_id"]), source_reservation_token=str(reservation["reservation_token"]),
            publish_date=date, content_part=content_part)
        draft_path = Path(draft["draft_path"])
        saved_draft = json.loads(draft_path.read_text(encoding="utf-8"))
        saved_draft["cover_images"] = cover_images
        draft_path.write_text(json.dumps(saved_draft, ensure_ascii=False, indent=2), encoding="utf-8")
        state.update({"draft_path": draft["draft_path"], "stage": "preparing"})
        _save_state(state_path, state)
        return _submit_preparation(state_path, state)


def get_production(workflow_id: str) -> dict:
    """通过流程 ID 查询当前任务，不向调用方暴露内部状态和稿件路径。"""
    state = _read_state(workflow_id)
    task_file = _state_path(workflow_id).with_name("production-task.json")
    if not task_file.exists():
        return {"workflow_id": workflow_id, "stage": state["stage"], "done": False}
    task = poll_task(task_path=json.loads(task_file.read_text(encoding="utf-8"))["task_path"])
    return {key: value for key, value in task.items() if key != "task_path"} | {
        "workflow_id": workflow_id, "stage": state["stage"]}


async def _wait_phase(workflow_id: str) -> dict:
    while True:
        result = await asyncio.to_thread(get_production, workflow_id)
        if result.get("done"):
            if result["status"] != "succeeded":
                raise RuntimeError(str(result.get("error")))
            return result["result"]
        await asyncio.sleep(1)


def _save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def continue_production(workflow_id: str, *, image_paths: list[str] | None = None,
                        production_source: str = "local_mcp") -> dict:
    """读取定稿分镜，搜索实拍素材、合成并上传 R2。"""
    state_path = _state_path(workflow_id)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["stage"] in {"reserving", "preparing"}:
        return finance_start_production(state["publish_date"], state["content_part"], generate_images=state["generate_images"])
    if state["stage"] == "completed":
        raise WorkflowStepError("该生产流程已经完成")
    config = finance_get_config()

    def work(progress=None):
        from workflows.finance.tools.materials import prepare_video_searches, download_selected_videos, prepare_image_materials
        current = json.loads(state_path.read_text(encoding="utf-8"))
        if current["stage"] == "awaiting_images":
            paths = image_paths if image_paths is not None else [
                request["output_path"] for request in current["storyboard_context"]["image_requests"]]
            materials = prepare_image_materials(current["draft_path"], paths)
            current.update({"material_manifest_path": materials["manifest_path"], "stage": "ready_to_render"})
            _save_state(state_path, current)
        if current["stage"] == "ready_to_search":
            storyboard_text = current["storyboard_context"]["storyboard_text"]
            searched = prepare_video_searches(current["draft_path"], storyboard_text,
                video_config=config["video_config"], progress=progress)
            materials = download_selected_videos(searched["context_path"], progress=progress)
            current.update({"storyboard_text": storyboard_text,
                            "material_manifest_path": materials["manifest_path"], "stage": "ready_to_render"})
            _save_state(state_path, current)
        if current["stage"] != "ready_to_render":
            raise WorkflowStepError("生产流程阶段不支持继续")
        result = d._finish_video_and_commit_source_usage(current["draft_path"],
            production_config=config["production_config"], material_manifest_path=current["material_manifest_path"],
            production_source=production_source, progress=progress)
        remote = upload_finance_assets_to_r2(result["manifest_path"])
        current["stage"] = "completed"
        _save_state(state_path, current)
        return {**result, "r2": remote, "stage": "completed", "workflow_id": workflow_id}
    task = runner_submit_task(cache_dir=state_path.parent, run_id=state["run_id"], step="continue_production", fn=work)
    _save_state(state_path.with_name("production-task.json"), {"task_path": task["task_path"]})
    return {"workflow_id": workflow_id, "status": task["status"]}


async def run(publish_date: str, content_part: int = 1, *,
              production_source: str = "local_mcp") -> dict:
    """读取稿库定稿与分镜，通过统一生产协议完成交付。"""
    started = await asyncio.to_thread(finance_start_production, publish_date, content_part)
    workflow_id = started["workflow_id"]
    state = _read_state(workflow_id)
    if state["stage"] == "completed":
        manifest = get_production(workflow_id)["result"]
        return {"manifest": manifest, "r2": manifest["r2"], "production_outputs": manifest["r2"]["production_outputs"]}
    if state["stage"] == "ready_to_render":
        await asyncio.to_thread(continue_production, workflow_id, production_source=production_source)
        manifest = await _wait_phase(workflow_id)
        return {"manifest": manifest, "r2": manifest["r2"], "production_outputs": manifest["r2"]["production_outputs"]}
    if state["stage"] != "ready_to_search":
        await _wait_phase(workflow_id)
    started = await asyncio.to_thread(continue_production, workflow_id,
        production_source=production_source)
    manifest = await _wait_phase(workflow_id)
    return {"manifest": manifest, "r2": manifest["r2"], "production_outputs": manifest["r2"]["production_outputs"]}
