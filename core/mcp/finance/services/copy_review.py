"""保存待审文案并校验宿主 Agent 审核结果，不调用外部文本模型。"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from ..errors import WorkflowStepError
from ..infrastructure.source_scripts import remember_rejected_ad_video, save_transcribed_scripts

_ROOT = Path(__file__).resolve().parents[4] / "cache" / "collect_finance_copy"
_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "copy-host-review.md"


def save_review_context(path: Path, context: dict) -> None:
    """原子保存待审状态，避免部分写入。"""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_review_context(context_path: str) -> tuple[Path, dict]:
    """只读取采集缓存中的审稿上下文。"""
    path = Path(context_path).resolve()
    if not path.is_relative_to(_ROOT.resolve()) or path.name != "copy-review.json":
        raise WorkflowStepError("context_path 必须是采集任务返回的审稿上下文")
    return path, json.loads(path.read_text(encoding="utf-8"))


def review_result(path: Path, context: dict) -> dict:
    """将待审原文和宿主指令返回给 Agent。"""
    pending = context["pending"]
    needs_more = any(a["saved_count"] < a["requested_count"] and a["next_index"] < len(a["works"])
                     for a in context.get("authors", []))
    completed = not pending and context["saved_count"] >= context["requested_count"]
    return {
        "context_path": str(path), "status": "awaiting_host_review" if pending else "completed" if completed else "incomplete",
        "requested_count": context["requested_count"], "saved_count": context["saved_count"],
        "skipped_ad_count": context["skipped_ad_count"], "pending": pending,
        "needs_more": needs_more and not pending, "completed": completed,
        "authors": [{k: a[k] for k in ("sec_user_id", "display_name", "requested_count", "saved_count")} for a in context.get("authors", [])],
        "failures": context.get("failures", []),
        "prompt": _PROMPT.read_text(encoding="utf-8") if pending else "",
    }


def _validate_review(original: str, review: dict) -> dict:
    kind = review.get("kind")
    if kind not in ("normal", "ad"):
        raise WorkflowStepError("审核 kind 只能为 normal 或 ad")
    reason = str(review.get("reason") or "").strip()
    if not reason:
        raise WorkflowStepError("审核结果必须包含 reason")
    text = str(review.get("text") or "").strip()
    if kind == "ad":
        if text:
            raise WorkflowStepError("整篇广告的 text 必须为空")
        return {"kind": kind, "text": "", "reason": reason}
    segments = review.get("ad_segments", [])
    if not isinstance(segments, list):
        raise WorkflowStepError("ad_segments 必须为原文广告片段数组")
    remaining = original
    for segment in segments:
        if not isinstance(segment, str) or not segment.strip() or segment not in remaining:
            raise WorkflowStepError("删除的广告片段必须逐字来自原文")
        remaining = remaining.replace(segment, "", 1)
    before = re.sub(r"[\s\W_]+", "", remaining)
    after = re.sub(r"[\s\W_]+", "", text)
    if not before or not after or not 0.85 <= len(after) / len(before) <= 1.15:
        raise WorkflowStepError("正文长度改动过大，不能总结或删减正常内容")
    if SequenceMatcher(None, before, after, autojunk=False).ratio() < 0.75:
        raise WorkflowStepError("正文改动过大，请保留原稿结构及信息")
    return {"kind": kind, "text": text, "reason": reason}


def submit_copy_reviews(context_path: str, response_text: str) -> dict:
    """验证宿主对当前批次的全部审核结果，再逐条幂等入库。"""
    path, context = load_review_context(context_path)
    data = json.loads(response_text)
    reviews = data.get("reviews") if isinstance(data, dict) else None
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        raise WorkflowStepError("必须提交 reviews 数组")
    by_id = {str(r.get("aweme_id") or ""): r for r in reviews}
    pending_ids = {r["aweme_id"] for r in context["pending"]}
    if len(by_id) != len(reviews) or set(by_id) != pending_ids:
        raise WorkflowStepError("审核结果必须与当前待审作品逐条对应，不得重复或遗漏")
    validated = {r["aweme_id"]: _validate_review(r["transcript_raw"], by_id[r["aweme_id"]]) for r in context["pending"]}
    for record in list(context["pending"]):
        reviewed = validated[record["aweme_id"]]
        if reviewed["kind"] == "ad":
            remember_rejected_ad_video(record["aweme_id"])
            context["skipped_ad_count"] += 1
        else:
            saved = {k: v for k, v in record.items() if k != "sec_user_id"}
            saved["transcript_corrected"] = reviewed["text"]
            save_transcribed_scripts([saved])
            context["saved_count"] += 1
            for author in context.get("authors", []):
                if author["sec_user_id"] == record.get("sec_user_id"):
                    author["saved_count"] += 1
        context.setdefault("reviewed", []).append({"aweme_id": record["aweme_id"], **reviewed})
        context["pending"].remove(record)
        save_review_context(path, context)
    return review_result(path, context)
