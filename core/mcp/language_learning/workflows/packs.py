"""预制词包的验收、入库与领取。"""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path


from ..infrastructure import (
    claim_language_learning_pack,
    release_language_learning_pack,
    commit_language_learning_pack,
    list_language_learning_pack_topics,
    upload_public_file,
)

from ..config import (
    MINIMUM_NEW_WORDS,
    WORD_HISTORY_DAYS,
    pack_cutout_cache_dir,
    production_dirs,
    production_run_id,
)
from ..errors import LanguageLearningError
from ..services.subject_cutouts import (
    approved_subject_cutout_paths, require_transparent_subject_sheet, review_subject_sheet, validate_subject_sheet,
)
from ..services.prompt_service import (
    build_subject_sheet_prompt, build_vocabulary_prompt, parse_vocabulary_response,
)
from ..services.vocabulary import list_recent_words, normalize_english_word
from .tasks import _map_error


def _require_new_pack_topic(topic: str) -> str:
    """在生成词表前查询 D1，拒绝已有图包主题。"""
    clean_topic = str(topic or "").strip()
    if clean_topic.casefold() in {item.strip().casefold() for item in list_language_learning_pack_topics()}:
        raise LanguageLearningError(f"预制图包主题 {clean_topic} 已存在，请更换新主题")
    return clean_topic


def language_learning_prepare_pack(topic: str) -> dict:
    """返回预制词包的双语词表 Prompt；供任意宿主 Agent 生成后提交。"""
    try:
        topic = _require_new_pack_topic(topic)
        return {
            "pack_id": f"language-pack-{uuid.uuid4().hex}",
            "topic": topic,
            "learning_modes": ["en-zh", "en-ko"],
            "vocabulary_prompt": build_vocabulary_prompt(topic, ["en-zh", "en-ko"], list_recent_words()),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_validate_pack_words(pack_id: str, topic: str, response_text: str) -> dict:
    """解析并校验预制词包的十个双语单词，不创建生产 run。"""
    try:
        if not re.fullmatch(r"language-pack-[a-f0-9]{32}", str(pack_id or "")):
            raise LanguageLearningError("pack_id 格式不正确，请使用 prepare_pack 返回的值")
        topic = _require_new_pack_topic(topic)
        words = parse_vocabulary_response(response_text, ["en-zh", "en-ko"])
        if str(words.get("_topic_english") or "").casefold() != str(topic or "").strip().casefold():
            raise LanguageLearningError("词包英文主题必须与 topic 完全一致")
        recent = {normalize_english_word(word) for word in list_recent_words()}
        english = [str(item.get("english") or "").strip() for item in words["en-zh"]]
        if len([word for word in english if normalize_english_word(word) not in recent]) < MINIMUM_NEW_WORDS:
            raise LanguageLearningError(f"词包至少需要 {MINIMUM_NEW_WORDS} 个最近 {WORD_HISTORY_DAYS} 天未使用的新词")
        subject_sheet_prompt = build_subject_sheet_prompt(topic, words["en-zh"])["subject_sheet_prompt"]
        return {"pack_id": pack_id, "topic": topic, "words": words, "word_count": len(english), "subject_sheet_prompt": subject_sheet_prompt}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_validate_pack_subject_sheet(
    pack_id: str,
    subject_sheet_path: str,
    visual_layout: dict,
) -> dict:
    """定位并裁切预制词包主题图，复用直接制作的主体图校验实现。"""
    try:
        if not re.fullmatch(r"language-pack-[a-f0-9]{32}", str(pack_id or "")):
            raise LanguageLearningError("pack_id 格式不正确，请使用 prepare_pack 返回的值")
        require_transparent_subject_sheet(subject_sheet_path)
        result = validate_subject_sheet(
            subject_sheet_path,
            visual_layout,
            pack_cutout_cache_dir(pack_id),
        )
        result["next_tool"] = (
            "language_learning_review_pack_subject_sheet"
            if result.get("valid") is True
            else "language_learning_validate_pack_subject_sheet"
        )
        return result
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_review_pack_subject_sheet(
    pack_id: str,
    subject_sheet_path: str,
    review: dict,
) -> dict:
    """提交预制词包整图验收结论；通过后才允许提交词包。"""
    try:
        if not re.fullmatch(r"language-pack-[a-f0-9]{32}", str(pack_id or "")):
            raise LanguageLearningError("pack_id 格式不正确，请使用 prepare_pack 返回的值")
        result = review_subject_sheet(
            subject_sheet_path,
            pack_cutout_cache_dir(pack_id),
            review,
        )
        if result.get("approved") is True:
            result["next_tool"] = "language_learning_commit_pack"
        else:
            result["next_tool"] = "language_learning_validate_pack_subject_sheet"
        return result
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_commit_pack(pack_id: str, topic: str, words: dict, subject_sheet_path: str) -> dict:
    """上传已切图并通过整图验收的十张透明主体图，将可复用词包写入 D1。"""
    try:
        if not re.fullmatch(r"language-pack-[a-f0-9]{32}", str(pack_id or "")):
            raise LanguageLearningError("pack_id 格式不正确")
        if not isinstance(words, dict) or any(len(words.get(mode) or []) != 10 for mode in ("en-zh", "en-ko")):
            raise LanguageLearningError("words 必须包含 en-zh 与 en-ko 两套各 10 个单词")
        path = Path(subject_sheet_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".png":
            raise LanguageLearningError(f"subject_sheet_path 必须是存在的透明 PNG：{path}")
        require_transparent_subject_sheet(path)
        cutout_paths = approved_subject_cutout_paths(path, pack_cutout_cache_dir(pack_id))
        urls = [
            upload_public_file(
                cutout_path,
                f"language-learning-packs/{pack_id}/subjects/{index:02d}.png",
                content_type="image/png",
            )["url"]
            for index, cutout_path in enumerate(cutout_paths, 1)
        ]
        pack = commit_language_learning_pack({"pack_id": pack_id, "topic": topic, "words": words, "image_urls": urls})
        return {"pack": pack, "next_tool": "language_learning_claim_pack"}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_claim_pack(publish_date: str) -> dict:
    """为 GitHub 生产领取一个包含十张已验收透明主体图的词包。"""
    try:
        run_id = production_run_id(publish_date)
        pack = claim_language_learning_pack(run_id=run_id, publish_date=publish_date)
        cache_root, output_root = production_dirs(run_id)
        cache_root.mkdir(parents=True, exist_ok=True); output_root.mkdir(parents=True, exist_ok=True)
        return {"run_id": run_id, "publish_date": publish_date, "cache_dir": str(cache_root), "output_dir": str(output_root), "pack": pack}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_release_pack(publish_date: str) -> dict:
    """失败或中断时归还词包；已经完整交付的生产保留使用记录。"""
    try:
        normalized_date = date.fromisoformat(str(publish_date).strip()).isoformat()
        return release_language_learning_pack(run_id=f"run-{normalized_date.replace('-', '')}", publish_date=normalized_date)
    except Exception as exc:
        raise _map_error(exc) from exc
