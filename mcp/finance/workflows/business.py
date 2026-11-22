"""财经采集定稿与视频生产的业务入口。"""
from __future__ import annotations

import workflows.finance.production as _production

from pathlib import Path
import hashlib
from typing import Literal
from typing_extensions import NotRequired, TypedDict

from . import articles as a, editorial as e, source_authors as authors
from .collect_copy import finance_start_collect_copy
from .collect_author_copies import finance_start_collect_author_copies
from .copy_review import finance_submit_copy_reviews, finance_start_continue_collect_author_copies
from .tasks import finance_poll_task
from workflows.finance.errors.exceptions import WorkflowStepError
from workflows.finance.parameters import (
    normalize_publish_date,
    PROJECT_CACHE_ROOT,
)
from media_factory_mcp.finance.infrastructure.collection import get_collection_review_stats
from media_factory_mcp.finance.resources.reference_image import image_generation_reference
from workflows.finance.infrastructure.scripts import list_editorial_drafts
from workflows.finance.tools.storyboard_images import save_storyboard_images, storyboard_hash
from tools.resources import package_resource_path
from tools.r2_files import upload_file
from PIL import Image


class CopyReview(TypedDict):
    """宿主一次提交的校对、广告审核与完整定稿。"""
    aweme_id: str
    kind: Literal["keep", "skip"]
    text: str
    reason: str
    ad_segments: NotRequired[list[str]]
    editorial: NotRequired[dict]


def _task(result: dict) -> dict:
    """统一后台任务的查询入口。"""
    return {**result, "poll_tool": "finance_get_task"} if "task_path" in result else result


def finance_get_config() -> dict:
    """读取配音、素材、片头、字幕与合成的唯一生产配置。"""
    return {**_production.finance_get_config(), "image_generation_reference": image_generation_reference()}


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
    """一次校验并保存宿主审核的原稿和完整 editorial。要稿入库，弃稿记录原因；配额不足自动启动续采，须继续审核至 completed=true。"""
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


def finance_start_production(publish_date: str, content_part: int=1, generate_images: bool = False) -> dict:
    """领取定稿并准备配音。默认搜索实拍；generate_images=true 时由宿主参考风格图生图，交回后合成。重复启动恢复原流程。"""
    result = _task(_production.finance_start_production(publish_date, content_part, generate_images=generate_images))
    if result["generate_images"]:
        result["image_generation_reference"] = image_generation_reference()
    return result


def finance_manage_cover(aweme_id: str, image_paths: dict[str, str] | None = None) -> dict:
    """领取横竖双封面任务；提交landscape、portrait两张成图后上传R2并登记。"""
    source = next(row for row in list_editorial_drafts(False)["records"] if row["aweme_id"] == aweme_id)
    editorial = source["editorial"]
    ratios = {"landscape": (16, 9), "portrait": (9, 16)}
    if image_paths is None:
        return {"aweme_id": aweme_id, "topic": editorial["topic"], "article": editorial["article"],
                "title": editorial["title"], "short_title": editorial["short_title"],
                "highlighted_words": editorial["cover_highlights"],
                "reference_image_paths": [str(package_resource_path("media_factory_mcp", "finance", "resources", name))
                                          for name in ("cover-style-reference.png", "cover-goose-reference.png")],
                "instructions": package_resource_path("media_factory_mcp", "finance", "prompts", "cover-image.md").read_text(encoding="utf-8"),
                "image_requests": [{"id": orientation, "aspect_ratio": f"{width}:{height}",
                                    "output_path": str(PROJECT_CACHE_ROOT / "finance" / "covers" / aweme_id / f"cover-{orientation}.png")}
                                   for orientation, (width, height) in ratios.items()]}
    if set(image_paths) != set(ratios):
        raise WorkflowStepError("请同时提交landscape横版与portrait竖版封面")
    for orientation, (expected_width, expected_height) in ratios.items():
        with Image.open(image_paths[orientation]) as picture:
            width, height = picture.size
            if abs(width / height - expected_width / expected_height) > 0.02:
                raise WorkflowStepError(f"{orientation}封面须为{expected_width}:{expected_height}")
    assets = {}
    for orientation, value in image_paths.items():
        path = Path(value).resolve()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stored = upload_file(path, f"finance/covers/{aweme_id}/{orientation}/{digest}{path.suffix.lower()}",
                             content_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg")
        assets[orientation] = {"key": stored["key"], "url": stored["url"], "sha256": digest,
                               "title": editorial["title"], "short_title": editorial["short_title"]}
    e.finance_save_editorial_drafts([{"aweme_id": aweme_id, "editorial": {**editorial, "cover_images": assets}}])
    return {"aweme_id": aweme_id, "cover_images": assets}


def finance_manage_storyboard_images(aweme_id: str, image_paths: list[str] | None = None) -> dict:
    """按未使用稿件准备生图清单；传入逐镜 image_paths 则上传 R2 并入库，供 GitHub Runner 下载使用。"""
    source = next(row for row in list_editorial_drafts(False)["records"] if row["aweme_id"] == aweme_id)
    editorial = source["editorial"]
    rows = [row for row in editorial["storyboard"].splitlines() if row.strip()][:-1]
    if image_paths is not None:
        if len(image_paths) != len(rows):
            raise WorkflowStepError(f"本稿需要 {len(rows)} 张分镜图片")
        return save_storyboard_images(aweme_id, editorial["storyboard"],
                                      {f"shot-{i:03d}": path for i, path in enumerate(image_paths, 1)})
    image_root = PROJECT_CACHE_ROOT / "finance" / "storyboard-images" / aweme_id / storyboard_hash(editorial["storyboard"])
    image_root.mkdir(parents=True, exist_ok=True)
    narration = [row for row in editorial["article"].splitlines() if row.strip()]
    return {"aweme_id": aweme_id, "image_generation_reference": image_generation_reference(),
            "image_requests": [
                {"id": f"shot-{i:03d}", "description": row.split("|", 1)[0], "narration": text,
                 "output_path": str(image_root / f"shot-{i:03d}.png")}
                for i, (row, text) in enumerate(zip(rows, narration), 1)]}










def finance_get_task(task_path: str = "", workflow_id: str = "") -> dict:
    """查询采集、配音、素材和合成任务；done=true 只代表当前步骤完成，采集须另核对 completed。"""
    if workflow_id:
        result = _production.get_production(workflow_id)
        if result["stage"] == "awaiting_images":
            result["image_generation_reference"] = image_generation_reference()
        return result
    result = finance_poll_task(task_path)
    if isinstance(result.get("result"), dict):
        result["result"] = _task(result["result"])
    return result


def finance_get_inventory(publish_date: str = "") -> dict:
    """只读查询稿件库存、近期话题和采集弃稿统计；指定日期时同时返回成片及待生产分片，不占用稿件。"""
    result = {"sources": a.finance_get_source_stats(), "topics": a.finance_get_topics(), "collection_review": get_collection_review_stats()}
    if publish_date:
        date = normalize_publish_date(publish_date)
        result.update({"outputs": a.finance_get_production_outputs(date),
                       "plan": a.finance_get_automation_plan(date)})
    return result


def finance_continue_production(workflow_id: str, image_paths: list[str] | None = None) -> dict:
    """按所选模式继续合成和 R2 交付。生图模式读取约定输出位置，或接收按镜头顺序排列的 image_paths。"""
    return _task(_production.continue_production(workflow_id, image_paths=image_paths))


BUSINESS_TOOLS = (
    finance_get_config, finance_manage_authors, finance_start_collection, finance_finalize_collection,
    finance_manage_drafts, finance_manage_cover, finance_manage_storyboard_images, finance_start_production, finance_continue_production, finance_get_task, finance_get_inventory,
)
