"""财经成片交付编排。"""
from __future__ import annotations
from ..infrastructure.gateways import mark_source_script_used
from ..config.settings import MCP_ID
from ..services.assemble_finance_video import finish_finance_video
from ..services.save_draft import save_source_usage
from ..services.save_draft import load_draft
from .common import _map_error

def _finish_video_and_commit_source_usage(
    draft_path: str,
    **kwargs,
) -> dict:
    """成片成功后才把占用中的数据库原稿标记为已使用。"""
    result = finish_finance_video(draft_path, **kwargs)
    _, draft = load_draft(draft_path, "财经稿件")
    if str(draft.get("source_database_status") or "") != "used":
        usage = mark_source_script_used(
            aweme_id=str(draft["source_aweme_id"]),
            workflow=MCP_ID,
            reservation_token=str(draft["source_reservation_token"]),
            run_id=str(draft["run_id"]),
            source_hook=str(draft["db_source_hook"]),
        )
        save_source_usage(draft_path, usage)
        result["source_usage"] = usage
    return result


def finance_get_video_editorial_input(draft_path: str, storyboard_text: str, production_config: dict) -> dict:
    """TTS 和分镜完成后返回字幕翻译、重点句排版、章节标题的输入，由宿主定稿后写入 production_config 再合成。MCP 不调用文本模型。"""
    from ..services.video_editorial import get_video_editorial_input
    try:
        return get_video_editorial_input(draft_path, storyboard_text, production_config)
    except Exception as exc:
        raise _map_error(exc) from exc
