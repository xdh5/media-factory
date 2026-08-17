"""财经文章到成品视频的一体化 Agent 工作流。"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Callable

from core.capabilities.bgm.select_bgm import select_bgm
from core.capabilities.intro.slide_in_shutter_filter import slide_in_shutter
from core.tools.image import generate_image
from core.tools.image.generate_image import _set_agent_image_generator
from core.tools.topic_history import recent_topics, reserve_topic, update_topic_status
from core.tools.topic_history._errors import DuplicateTopicError
from core.tools.tts.compose import compose as compose_tts
from core.tools.video import compose_video, concat_segments, mix_bgm, prepend_cover_frame

from ._constants import (
    BGM_ID,
    COVER_PROMPT_PATH,
    DEFAULT_CACHE_ROOT,
    DEFAULT_DATABASE_PATH,
    DEFAULT_OUTPUT_ROOT,
    FINANCE_PROMPT_PATH,
    FORMAT_PROMPT_PATH,
    TEXT2IMAGE_PROMPT_PATH,
    TOPIC_DEDUPLICATION_DAYS,
    TTS_VOICE,
    VIDEO_RADIO,
    VIDEO_SIZE,
    VISUAL_STYLE,
    WORKFLOW_ID,
)
from ._errors import AgentOutputFormatError, AgentTextCapabilityError, WorkflowStepError
from ._product_store import save_product

__all__ = ["run_finance_workflow"]

AgentTextGenerator = Callable[[dict], object]
_agent_text_generator: AgentTextGenerator | None = None


def _set_agent_text_generator(generator: AgentTextGenerator | None) -> None:
    """由宿主注入当前 Agent 的文本能力，不作为工作流参数暴露。"""
    global _agent_text_generator
    if generator is not None and not callable(generator):
        raise TypeError("当前 Agent 文本适配器必须可调用")
    _agent_text_generator = generator


def _set_agent_image_capability(generator: Callable[[dict], object] | None) -> None:
    """由宿主注入当前 Agent 的生图能力；没有能力时传 None，生图 Tool 会直走方舟。"""
    _set_agent_image_generator(generator)


def _read_prompt(path: Path) -> str:
    if not path.is_file():
        raise WorkflowStepError(f"工作流 Prompt 不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def _render(template: str, **values: object) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def _agent_text(task: str, prompt: str) -> str:
    if _agent_text_generator is None:
        raise AgentTextCapabilityError(
            "Finance 工作流需要当前 Agent 的文本能力，请先调用私有 _set_agent_text_generator() 注入"
        )
    try:
        result = _agent_text_generator({"task": task, "prompt": prompt})
    except Exception as exc:
        raise AgentTextCapabilityError(f"当前 Agent 执行 {task} 失败：{type(exc).__name__}: {exc}") from exc
    if isinstance(result, dict):
        result = result.get("text") or result.get("output_text") or result.get("content")
    text = str(result or "").strip()
    if not text:
        raise AgentTextCapabilityError(f"当前 Agent 执行 {task} 后没有返回文本")
    return text


def _clean_single_line(value: str) -> str:
    lines = [line.strip().strip("#*- ") for line in value.splitlines() if line.strip()]
    if not lines:
        raise AgentOutputFormatError("Agent 没有返回可用话题")
    return lines[0]


def _choose_topic(database_path: Path) -> dict:
    recent = recent_topics(database_path, WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    recent_text = "\n".join(f"- {item['topic']}" for item in recent) or "（最近 30 天没有记录）"
    prompt = (
        "请任选一个适合中文短视频的理财或财经话题。可以是长期有效的理财常识、经济现象或风险提醒。\n"
        "不得与下面最近 30 天的话题重复或只是换一种说法：\n"
        f"{recent_text}\n\n"
        "只输出一个话题，不要编号、解释、标题符号或 Markdown。"
    )
    for _ in range(5):
        topic = _clean_single_line(_agent_text("选择财经话题", prompt))
        try:
            return reserve_topic(database_path, WORKFLOW_ID, topic, TOPIC_DEDUPLICATION_DAYS)
        except DuplicateTopicError:
            prompt += f"\n刚才生成的“{topic}”仍然重复，请换一个完全不同的话题。"
    raise WorkflowStepError("连续 5 次都生成了最近 30 天内的重复话题")


def _parse_metadata(value: str) -> dict:
    line = next((line.strip() for line in value.splitlines() if "|" in line), "")
    fields = [field.strip().lstrip("#") for field in line.split("|")]
    if len(fields) != 6 or any(not field for field in fields):
        raise AgentOutputFormatError("标题标签必须严格输出：长标题|短标题|标签一|标签二|标签三|标签四")
    if not 12 <= len(fields[0]) <= 26:
        raise AgentOutputFormatError("中文长标题必须为 12～26 个字符")
    if not 6 <= len(fields[1]) <= 16:
        raise AgentOutputFormatError("中文短标题必须为 6～16 个字符")
    if len(set(fields[2:])) != 4:
        raise AgentOutputFormatError("四个标签必须互不重复")
    return {"title": fields[0], "short_title": fields[1], "hashtags": fields[2:]}


def _timeline_table(timeline: list[dict]) -> str:
    return "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)


def _parse_motion(value: str) -> dict:
    parts = [part.strip() for part in value.split("^")]
    if len(parts) != 8:
        raise AgentOutputFormatError(f"动效参数必须包含 8 个 ^ 分隔值：{value}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise AgentOutputFormatError(f"动效参数必须全部是数字：{value}") from exc
    if numbers[6] != 0 or numbers[7] != 0:
        raise AgentOutputFormatError("分镜淡入和淡出必须固定为 0")
    return {
        "zoom_from": numbers[0],
        "zoom_to": numbers[1],
        "pan_from_x": numbers[2],
        "pan_from_y": numbers[3],
        "pan_to_x": numbers[4],
        "pan_to_y": numbers[5],
    }


def _parse_storyboard(value: str, timeline: list[dict]) -> list[dict]:
    timeline_by_id = {item["id"]: item for item in timeline}
    shots: list[dict] = []
    used_ids: list[str] = []
    for line in value.splitlines():
        if "|" not in line:
            continue
        fields = [field.strip() for field in line.split("|", 4)]
        if len(fields) != 5 or fields[2].upper() != "IMAGE":
            continue
        line_ids = [item.strip() for item in fields[0].split(",") if item.strip()]
        if not line_ids or any(line_id not in timeline_by_id for line_id in line_ids):
            raise AgentOutputFormatError(f"分镜包含未知台词 ID：{fields[0]}")
        indices = [list(timeline_by_id).index(line_id) for line_id in line_ids]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise AgentOutputFormatError(f"同一镜头只能合并相邻台词：{fields[0]}")
        selected = [timeline_by_id[line_id] for line_id in line_ids]
        start = selected[0]["start"]
        end = selected[-1]["end"]
        if end - start > 5.01:
            raise AgentOutputFormatError(f"镜头 {fields[0]} 的真实 TTS 时长超过 5 秒")
        shots.append({
            "id": f"shot-{len(shots) + 1:03d}",
            "line_ids": line_ids,
            "audio_start": start,
            "audio_end": end,
            "duration": round(end - start, 6),
            "subtitle": " ".join(item["text"] for item in selected),
            "prompt": fields[3],
            "motion": _parse_motion(fields[4]),
        })
        used_ids.extend(line_ids)
    expected_ids = [item["id"] for item in timeline]
    if not shots or used_ids != expected_ids:
        raise AgentOutputFormatError(
            "分镜必须按顺序且不重不漏地覆盖全部台词 ID",
            {"expected_ids": expected_ids, "actual_ids": used_ids},
        )
    return shots


def _hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_first_shot_cached(
    shot: dict,
    tts_path: Path,
    segment_path: Path,
    *,
    force: bool,
) -> bool:
    metadata_path = segment_path.with_suffix(".json")
    payload = {
        "version": 1,
        "image_sha256": _hash_file(shot["image_path"]),
        "tts_sha256": _hash_file(tts_path),
        "audio_start": shot["audio_start"],
        "audio_end": shot["audio_end"],
        "subtitle": shot["subtitle"],
        "motion": shot["motion"],
    }
    signature = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not force and segment_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("signature") == signature:
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    slide_in_shutter(
        shot["image_path"],
        tts_path,
        segment_path,
        audio_start=shot["audio_start"],
        audio_end=shot["audio_end"],
        subtitle=shot["subtitle"],
        motion=shot["motion"],
    )
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"signature": signature, "shot_id": shot["id"]}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)
    return False


def run_finance_workflow(
    *,
    database_path: str | Path | None = None,
    draft_path: str | Path | None = None,
    article_confirmed: bool = False,
    force_shot_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """执行财经工作流；稿件确认前暂停，成品完成后等待发布确认。"""
    if not isinstance(article_confirmed, bool):
        raise WorkflowStepError("article_confirmed 必须是布尔值")
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    record: dict | None = None
    try:
        if draft_path is None:
            record = _choose_topic(database)
            run_id = f"run-{record['id']:06d}"
            cache_root = (DEFAULT_CACHE_ROOT / run_id).resolve()
            output_root = (DEFAULT_OUTPUT_ROOT / run_id).resolve()
            cache_root.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

            finance_prompt = _render(_read_prompt(FINANCE_PROMPT_PATH), topic=record["topic"])
            article = _agent_text("生成财经正文", finance_prompt)
            metadata_prompt = _read_prompt(FORMAT_PROMPT_PATH) + f"\n\n正文：\n{article}"
            metadata = _parse_metadata(_agent_text("生成标题和标签", metadata_prompt))
            saved_draft_path = cache_root / "draft.json"
            draft = {
                "version": 1,
                "status": "awaiting_article_confirmation",
                "confirmation_required": "article",
                "database_path": str(database),
                "topic": record["topic"],
                "run_id": run_id,
                "topic_record_id": record["id"],
                "article": article,
                **metadata,
                "cache_dir": str(cache_root),
                "output_dir": str(output_root),
                "draft_path": str(saved_draft_path),
            }
            saved_draft_path.write_text(
                json.dumps(draft, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 即使调用方提前传了 article_confirmed，也必须先把本次实际稿件交给用户查看。
            return draft

        saved_draft_path = Path(draft_path).resolve()
        if not saved_draft_path.is_file():
            raise WorkflowStepError(f"待确认稿件不存在：{saved_draft_path}")
        try:
            draft = json.loads(saved_draft_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowStepError(f"读取待确认稿件失败：{saved_draft_path}。{exc}") from exc
        required_draft_fields = {
            "topic", "run_id", "topic_record_id", "article", "title", "short_title",
            "hashtags", "cache_dir", "output_dir",
        }
        missing_fields = sorted(required_draft_fields.difference(draft))
        if missing_fields:
            raise WorkflowStepError(
                f"待确认稿件缺少字段：{missing_fields}",
                {"draft_path": str(saved_draft_path)},
            )
        record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
        run_id = str(draft["run_id"])
        article = str(draft["article"])
        metadata = {
            "title": str(draft["title"]),
            "short_title": str(draft["short_title"]),
            "hashtags": list(draft["hashtags"]),
        }
        cache_root = Path(draft["cache_dir"]).resolve()
        output_root = Path(draft["output_dir"]).resolve()
        if not article_confirmed:
            return draft

        image_cache_root = (cache_root / "images").resolve()
        cache_root.mkdir(parents=True, exist_ok=True)
        image_cache_root.mkdir(parents=True, exist_ok=True)
        output_root.mkdir(parents=True, exist_ok=True)

        cover_prompt = _render(
            _read_prompt(COVER_PROMPT_PATH),
            size=VIDEO_SIZE,
            radio=VIDEO_RADIO,
            title=metadata["short_title"],
            style=VISUAL_STYLE,
        )
        cover_result = generate_image(
            cover_prompt, VISUAL_STYLE, VIDEO_RADIO, VIDEO_SIZE,
            force_regenerate=force_images,
            cache_dir=image_cache_root,
        )

        tts_path = cache_root / "narration.wav"
        tts_result = compose_tts(article, tts_path, TTS_VOICE)
        storyboard_prompt = _render(
            _read_prompt(TEXT2IMAGE_PROMPT_PATH),
            style=VISUAL_STYLE,
            radio=VIDEO_RADIO,
            size=VIDEO_SIZE,
        ) + "\n\n" + _timeline_table(tts_result["timeline"])
        shots = _parse_storyboard(_agent_text("生成视频分镜", storyboard_prompt), tts_result["timeline"])

        forced = set(force_shot_ids or [])
        unknown_forced = forced.difference(shot["id"] for shot in shots)
        if unknown_forced:
            raise WorkflowStepError(f"要重做的镜头不存在：{sorted(unknown_forced)}")
        for shot in shots:
            image_result = generate_image(
                shot["prompt"], VISUAL_STYLE, VIDEO_RADIO, VIDEO_SIZE,
                force_regenerate=force_images or shot["id"] in forced,
                cache_dir=image_cache_root,
            )
            shot["image_path"] = image_result["output_path"]

        segment_dir = cache_root / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        first_shot = shots[0]
        first_segment = segment_dir / f"{first_shot['id']}.mp4"
        first_shot["cache_hit"] = _render_first_shot_cached(
            first_shot,
            tts_path,
            first_segment,
            force=first_shot["id"] in forced,
        )
        segment_paths = [str(first_segment)]
        if len(shots) > 1:
            standard_output = cache_root / "standard-shots.mp4"
            standard_result = compose_video(
                [
                    {
                        "id": shot["id"],
                        "image_path": shot["image_path"],
                        "audio_path": str(tts_path),
                        "audio_start": shot["audio_start"],
                        "audio_end": shot["audio_end"],
                        "subtitle": shot["subtitle"],
                        "motion": shot["motion"],
                    }
                    for shot in shots[1:]
                ],
                standard_output,
                cache_root / "shot-cache",
                size=VIDEO_SIZE,
                force_shot_ids=[shot_id for shot_id in forced if shot_id != first_shot["id"]],
            )
            segment_paths.append(standard_result["output_path"])

        assembled_path = cache_root / "assembled.mp4"
        concat_segments(segment_paths, assembled_path)
        with_cover_path = cache_root / "with-cover.mp4"
        prepend_cover_frame(cover_result["output_path"], assembled_path, with_cover_path, size=VIDEO_SIZE)
        bgm = select_bgm(id=BGM_ID)
        final_path = output_root / "video.mp4"
        mix_bgm(with_cover_path, bgm["path"], final_path)

        publish_copy = "【" + metadata["short_title"] + " " + " ".join(
            f"#{tag.lstrip('#')}" for tag in metadata["hashtags"]
        ) + "】"
        title_path = output_root / "title.txt"
        publish_copy_path = output_root / "publish-copy.txt"
        title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
        publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")

        product_record = save_product(
            database,
            run_id=run_id,
            topic_record_id=record["id"],
            topic=record["topic"],
            title=metadata["title"],
            short_title=metadata["short_title"],
            hashtags=metadata["hashtags"],
            publish_copy=publish_copy,
            video_path=final_path,
            output_dir=output_root,
            cache_dir=cache_root,
        )

        manifest = {
            "status": "awaiting_publish_confirmation",
            "confirmation_required": "publish",
            "topic": record["topic"],
            "run_id": run_id,
            "article": article,
            **metadata,
            "cover_path": cover_result["output_path"],
            "video_path": str(final_path),
            "output_dir": str(output_root),
            "title_path": str(title_path),
            "publish_copy": publish_copy,
            "publish_copy_path": str(publish_copy_path),
            "created_at": product_record["created_at"],
            "product_record_id": product_record["id"],
            "topic_record_id": record["id"],
            "shots": shots,
        }
        manifest_path = cache_root / "manifest.json"
        manifest["manifest_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        update_topic_status(database, record["id"], "completed")
        return manifest
    except Exception:
        if record is not None:
            update_topic_status(database, record["id"], "failed")
        raise
