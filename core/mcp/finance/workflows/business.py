"""财经采集定稿与视频生产的业务入口。"""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from typing_extensions import NotRequired, TypedDict

from . import articles as a, materials as m, delivery as d, editorial as e, source_authors as authors
from .collect_copy import finance_start_collect_copy
from .collect_author_copies import finance_start_collect_author_copies
from .copy_review import finance_submit_copy_reviews, finance_start_continue_collect_author_copies
from .tasks import finance_poll_task
from ..errors import WorkflowStepError
from ..config.settings import (
    MATERIAL_AGENT_REFERENCE, MATERIAL_STOCK_VIDEO, MATERIAL_STRATEGIES, normalize_publish_date,
)
from ..infrastructure.gateways import runner_submit_task
from ..services.save_draft import load_draft
from ..services.storyboard import prepare_storyboard
from ..services.upload_to_r2 import upload_finance_assets_to_r2


class CopyReview(TypedDict):
    """宿主一次提交的校对、广告审核与完整定稿。"""
    aweme_id: str
    kind: Literal["normal", "ad"]
    text: str
    reason: str
    ad_segments: NotRequired[list[str]]
    editorial: NotRequired[dict]


def _task(result: dict) -> dict:
    """统一后台任务的查询入口。"""
    return {**result, "poll_tool": "finance_get_task"} if "task_path" in result else result


def finance_get_config() -> dict:
    """读取配音、素材、片头、字幕与合成的唯一生产配置。"""
    return a.finance_get_production_config()


def finance_manage_authors(action: str = "list", profile_url: str = "", display_name: str = "") -> dict:
    """管理采集作者。action 为 list、add、remove；增删后返回最新名单。"""
    if action == "list":
        return authors.finance_list_source_authors()
    if action == "add":
        changed = authors.finance_add_source_author(profile_url, display_name)
    elif action == "remove":
        changed = authors.finance_remove_source_author(profile_url)
    else:
        raise WorkflowStepError("作者操作必须为 list、add 或 remove")
    return {**changed, **authors.finance_list_source_authors()}


def finance_start_collection(share_text: str = "", count: int = 0, context_path: str = "") -> dict:
    """按单条链接、作者配额或已有上下文采集，三选一。完成后返回待审原文，由宿主去广告、改写和定稿，尚未入库。"""
    if sum((bool(share_text), count > 0, bool(context_path))) != 1:
        raise WorkflowStepError("必须且只能提供分享链接、正整数数量或续采上下文")
    if context_path:
        return _task(finance_start_continue_collect_author_copies(context_path))
    if share_text:
        return _task(finance_start_collect_copy(share_text, "财经"))
    return _task(finance_start_collect_author_copies(count))


def finance_finalize_collection(context_path: str, reviews: list[CopyReview]) -> dict:
    """一次校验并保存宿主审核的原稿和完整 editorial。整篇广告剔除；配额不足自动启动续采，须继续审核至 completed=true。"""
    result = finance_submit_copy_reviews(context_path, reviews)
    if result.get("needs_more"):
        result["continuation"] = _task(finance_start_continue_collect_author_copies(context_path))
    return result


def finance_manage_drafts(action: str = "list", missing_only: bool = True,
                           records: list[dict] | None = None) -> dict:
    """读取或保存未使用稿件完整定稿。action 为 list 或 save；不占用、不修改已使用稿件。"""
    if action == "list":
        return {**e.finance_list_editorial_drafts(missing_only), **a.finance_get_topics()}
    if action == "save" and records is not None:
        return e.finance_save_editorial_drafts(records)
    raise WorkflowStepError("稿件操作必须为 list 或携带 records 的 save")


def finance_start_production(publish_date: str, content_part: int = 1,
                              material_strategy: str = "", draft_path: str = "") -> dict:
    """明确计划日期后领取定稿、保存生产稿、后台生成配音及分镜输入。恢复时传已有 draft_path，不重新领取稿件。宿主据此写分镜，不重写定稿。"""
    date = normalize_publish_date(publish_date)
    if content_part < 1:
        raise WorkflowStepError("内容分片必须为正整数")
    config = finance_get_config()
    strategy = material_strategy or config["material_strategy"]
    if strategy not in MATERIAL_STRATEGIES:
        raise WorkflowStepError("素材策略必须为 stock_video 或 agent_reference")
    if draft_path:
        _, stored = load_draft(draft_path, "财经稿件")
        if stored["publish_date"] != date or int(stored.get("content_part", 1)) != content_part:
            raise WorkflowStepError("恢复稿件的计划日期和分片必须与请求一致")
        draft = {"draft_path": draft_path}
        source = {"aweme_id": stored["source_aweme_id"], "editorial": {
            key: stored[key] for key in ("topic", "article", "title", "short_title", "hashtags")}}
    else:
        selected = a.finance_get_source_script()
        source, reservation = selected["source"], selected["reservation"]
        editorial = source["editorial"]
        draft = a.finance_save_draft(
            **{key: editorial[key] for key in ("topic", "article", "title", "short_title", "hashtags",
               "cover_lines", "cover_highlights", "source_hook", "db_source_hook")},
            source_aweme_id=str(source["aweme_id"]),
            source_reservation_token=str(reservation["reservation_token"]),
            publish_date=date, content_part=content_part)
        draft_path = draft["draft_path"]
        _, stored = load_draft(draft_path, "财经稿件")

    def work():
        result = prepare_storyboard(draft_path, tts_config=config["tts_config"], material_strategy=strategy)
        return {**result, "draft": draft, "source": source}
    return _task(runner_submit_task(cache_dir=Path(stored["cache_dir"]), run_id=stored["run_id"],
                                    step="prepare_production", fn=work))


def finance_prepare_visuals(draft_path: str, storyboard_text: str,
                             material_strategy: str = "", image_config: dict | None = None) -> dict:
    """提交宿主分镜，按配置返回生图任务或启动实拍素材搜索。耗时搜索返回统一后台任务。"""
    config = finance_get_config()
    strategy = material_strategy or config["material_strategy"]
    if strategy == MATERIAL_STOCK_VIDEO:
        return _task(m.finance_start_video_search(draft_path, storyboard_text, config["video_config"]))
    if strategy == MATERIAL_AGENT_REFERENCE:
        return m.finance_prepare_images(draft_path, storyboard_text, image_config or {})
    raise WorkflowStepError("素材策略必须为 stock_video 或 agent_reference")


def finance_submit_visuals(context_path: str, material_strategy: str,
                            images: list[dict] | None = None,
                            selections: list[dict] | None = None) -> dict:
    """图片保存并完成入库；实拍按明确选片或默认尺寸顺序下载。只准备素材，不自动合成，不调用模型选片。"""
    if material_strategy == MATERIAL_AGENT_REFERENCE:
        return m.submit_reference_images(context_path, images or [])
    if material_strategy == MATERIAL_STOCK_VIDEO:
        return _task(m.start_download_videos(context_path, selections))
    raise WorkflowStepError("素材策略必须为 stock_video 或 agent_reference")


def finance_prepare_editorial(draft_path: str, storyboard_text: str,
                               production_config: dict | None = None) -> dict:
    """返回真实配音、字幕和章节输入，宿主生成重点句 groups、翻译 translations 和章节 titles，合入配置后合成。"""
    return d.finance_get_video_editorial_input(draft_path, storyboard_text,
        production_config if production_config is not None else finance_get_config()["production_config"])


def finance_start_render(draft_path: str, production_config: dict, material_manifest_path: str,
                          storyboard_text: str, upload_r2: bool = True,
                          production_source: str = "local_mcp", intro_image_path: str = "",
                          force_shot_ids: list[str] | None = None) -> dict:
    """后台合成，成功后标记原稿已使用；默认上传 R2 并返回本地成片与远程产物。必须提供宿主定稿的字幕、重点句和章节。"""
    from ..services.video_editorial import validate_video_editorial
    validate_video_editorial(draft_path, storyboard_text, production_config)
    if production_source not in {"local_mcp", "github_workflow"}:
        raise WorkflowStepError("生产来源必须为 local_mcp 或 github_workflow")
    _, draft = load_draft(draft_path, "财经稿件")
    def work(progress=None):
        result = d._finish_video_and_commit_source_usage(draft_path,
            production_config=production_config, material_manifest_path=material_manifest_path,
            storyboard_text=storyboard_text, production_source=production_source,
            intro_image_path=intro_image_path or None, force_shot_ids=force_shot_ids, progress=progress)
        if upload_r2:
            remote = upload_finance_assets_to_r2(result["manifest_path"])
            return {**result, "r2": remote}
        return result
    return _task(runner_submit_task(cache_dir=Path(draft["cache_dir"]), run_id=draft["run_id"],
                                    step="render_and_deliver", fn=work))


def finance_get_task(task_path: str) -> dict:
    """查询采集、配音、素材和合成任务；done=true 只代表当前步骤完成，采集须另核对 completed。"""
    result = finance_poll_task(task_path)
    if isinstance(result.get("result"), dict):
        result["result"] = _task(result["result"])
    return result


def finance_get_inventory(publish_date: str = "") -> dict:
    """只读查询稿件库存、近期话题；指定日期时同时返回成片及待生产分片，不占用稿件。"""
    result = {"sources": a.finance_get_source_stats(), "topics": a.finance_get_topics()}
    if publish_date:
        date = normalize_publish_date(publish_date)
        result.update({"outputs": a.finance_get_production_outputs(date),
                       "plan": a.finance_get_automation_plan(date)})
    return result


BUSINESS_TOOLS = (
    finance_get_config, finance_manage_authors, finance_start_collection, finance_finalize_collection,
    finance_manage_drafts, finance_start_production, finance_prepare_visuals, finance_submit_visuals,
    finance_prepare_editorial, finance_start_render, finance_get_task, finance_get_inventory,
)
