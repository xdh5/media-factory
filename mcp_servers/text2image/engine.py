"""文生图：旁白、分镜解析与出片。"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from core.capabilities.bgm import select_bgm
from core.capabilities.intro import (
    INTRO_RENDERER_VERSION,
    VideoRenderError,
    page_flip,
    slide_in_shutter,
)
from core.tools.cover import CoverError, generate_cover
from core.tools.tts import generate_tts

from ._constants import STORYBOARD_TEXT_FILE_NAME, TEXT2IMAGE_PROMPT_PATH
from ._errors import AgentOutputFormatError, WorkflowStepError
from ._line import Text2ImageLine, load_line
from .assemble import assemble_text2image_video


def read_prompt(path: Path) -> str:
    if not path.is_file():
        raise WorkflowStepError(f"工作流 Prompt 不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def render_template(template: str, **values: object) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def assemble_article_prompt(line: Text2ImageLine) -> str:
    hooks = read_prompt(line.hooks_path)
    example_files = sorted(
        path for path in line.examples_dir.glob("*.txt") if path.name != line.hooks_path.name
    )
    if not example_files:
        raise WorkflowStepError(f"找不到正文范文：{line.examples_dir}")
    examples = "\n\n".join(f"### {path.stem}\n{read_prompt(path)}" for path in example_files)
    return render_template(read_prompt(line.article_prompt_path), hooks=hooks, article_examples=examples)


def parse_metadata(value: str) -> dict:
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


def timeline_table(timeline: list[dict]) -> str:
    return "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)


def storyboard_prompt(line: Text2ImageLine, timeline: list[dict]) -> str:
    shared_prompt = read_prompt(TEXT2IMAGE_PROMPT_PATH)
    private_rules = read_prompt(line.shot_image_rules_path)
    template = f"{shared_prompt}\n\n## 业务线专属画面规则\n\n{private_rules}"
    return render_template(
        template,
        style=line.visual_style,
        radio=line.video_radio,
        size=line.video_size,
    ) + "\n\n" + timeline_table(timeline)


def compose_tts(line: Text2ImageLine, article: str, cache_root: Path) -> dict:
    script = [
        {"text": line_text.strip(), "voice": line.tts_voice}
        for line_text in article.splitlines()
        if line_text.strip()
    ]
    return generate_tts(
        script,
        cache_root / "narration.wav",
        rate=line.tts_rate,
        trim_trailing_silence=line.tts_trim_trailing_silence,
    )


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


def parse_storyboard(value: str, timeline: list[dict]) -> list[dict]:
    timeline_by_id = {item["id"]: item for item in timeline}
    shots: list[dict] = []
    used_ids: list[str] = []
    for row in value.splitlines():
        if "|" not in row:
            continue
        fields = [field.strip() for field in row.split("|", 4)]
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


def _resolve_intro_sfx(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_file():
        return path
    parent = path.parent
    stem = path.stem
    for suffix in (".wav", ".mp3", ".m4a", ".aac", ".ogg"):
        candidate = parent / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return path


def _pick_page_flip_images(image_paths: list[str], last_path: str, seed: str) -> list[str]:
    resolved = [str(Path(path).resolve()) for path in image_paths]
    last = str(Path(last_path).resolve())
    others = [path for path in resolved if path != last]
    pool = others or resolved
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    pages: list[str] = []
    for _ in range(8):
        choices = [path for path in pool if not pages or path != pages[-1]] or pool
        pages.append(rng.choice(choices))
    pages.append(last)
    return pages


def _render_first_shot_cached(
    line: Text2ImageLine,
    shots: list[dict],
    shot: dict,
    tts_path: Path,
    segment_path: Path,
    *,
    force: bool,
) -> bool:
    intro = (line.intro or "slide_in_shutter").strip()
    page_images: list[str] = []
    sfx_path = _resolve_intro_sfx(line.intro_sfx_path)
    if intro == "page_flip":
        pool = [str(item["image_path"]) for item in shots]
        seed = "|".join(
            [line.id, shot["id"]] + [_hash_file(path) for path in pool]
        )
        page_images = _pick_page_flip_images(pool, shot["image_path"], seed)
    metadata_path = segment_path.with_suffix(".json")
    payload = {
        "version": 2,
        "intro": intro,
        "intro_renderer_version": INTRO_RENDERER_VERSION,
        "image_sha256": _hash_file(shot["image_path"]),
        "page_image_sha256": [_hash_file(path) for path in page_images],
        "sfx_sha256": _hash_file(sfx_path) if intro == "page_flip" and sfx_path and sfx_path.is_file() else None,
        "tts_sha256": _hash_file(tts_path),
        "audio_start": shot["audio_start"],
        "audio_end": shot["audio_end"],
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
    try:
        if intro == "page_flip":
            if sfx_path is None or not sfx_path.is_file():
                expected = line.intro_sfx_path or Path("page_flip.wav")
                raise WorkflowStepError(
                    f"人生文案翻页音效不存在：{expected}。"
                    "请把音效文件放到 workflows/life_copy/static/page_flip.wav（或同名 mp3）"
                )
            page_flip(
                page_images,
                tts_path,
                segment_path,
                sfx_path,
                audio_start=shot["audio_start"],
                audio_end=shot["audio_end"],
            )
        elif intro == "slide_in_shutter":
            slide_in_shutter(
                shot["image_path"],
                tts_path,
                segment_path,
                audio_start=shot["audio_start"],
                audio_end=shot["audio_end"],
                motion=shot["motion"],
            )
        else:
            raise WorkflowStepError(
                f"未知开场动画类型：{intro!r}。当前支持 slide_in_shutter、page_flip"
            )
    except VideoRenderError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"signature": signature, "shot_id": shot["id"]}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)
    return False


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(
    image_metadata: dict,
    cache_root: Path,
    storyboard_text: str | None,
) -> str:
    saved = str(image_metadata.get("storyboard_text") or "").strip()
    saved_path = Path(str(image_metadata.get("storyboard_path") or "")).resolve()
    if not saved and saved_path.is_file():
        saved = saved_path.read_text(encoding="utf-8").strip()
    fallback_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    if not saved and fallback_path.is_file():
        saved = fallback_path.read_text(encoding="utf-8").strip()
    if saved:
        expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
        if expected_hash and _storyboard_hash(saved) != expected_hash:
            raise WorkflowStepError(
                "已保存的分镜文本损坏，请重新调用 text2image_prepare_images",
                {"storyboard_sha256": expected_hash},
            )
        return saved
    fallback = str(storyboard_text or "").strip()
    if not fallback:
        raise WorkflowStepError(
            "生图清单里没有分镜文本。请重新调用 text2image_prepare_images，出片不必再传 storyboard_text"
        )
    expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
    if expected_hash and _storyboard_hash(fallback) != expected_hash:
        raise WorkflowStepError(
            "传入的 storyboard_text 与生图时不一致。请不要重写分镜，重新调用 text2image_prepare_images 后直接 text2image_finish_video",
            {"storyboard_sha256": expected_hash, "received_sha256": _storyboard_hash(fallback)},
        )
    return fallback


def finish_video(
    draft_path: str | Path,
    storyboard_text: str | None = None,
    *,
    user_confirmed: bool,
    image_manifest_path: str | Path,
    force_shot_ids: list[str] | None = None,
) -> dict:
    from .draft import load_draft

    if user_confirmed is not True:
        from ._errors import ConfirmationRequiredError

        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    resolved_draft, draft = load_draft(draft_path, "待确认稿件")
    line = load_line(str(draft.get("line") or ""))
    required_draft_fields = {
        "topic", "run_id", "topic_record_id", "article", "title", "short_title",
        "hashtags", "cache_dir", "output_dir",
    }
    missing_fields = sorted(required_draft_fields.difference(draft))
    if missing_fields:
        raise WorkflowStepError(
            f"待确认稿件缺少字段：{missing_fields}",
            {"draft_path": str(resolved_draft)},
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
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    tts_result = compose_tts(line, article, cache_root)
    tts_path = Path(tts_result["output_path"])
    resolved_image_manifest = Path(image_manifest_path).resolve()
    if not resolved_image_manifest.is_file():
        raise WorkflowStepError(f"Agent 生图清单不存在：{resolved_image_manifest}")
    try:
        image_manifest = json.loads(resolved_image_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取 Agent 生图清单失败：{resolved_image_manifest}。{exc}") from exc
    image_metadata = image_manifest.get("metadata")
    if not isinstance(image_metadata, dict):
        raise WorkflowStepError("Agent 生图清单缺少 metadata")
    if Path(str(image_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("Agent 生图清单不属于当前稿件，请重新调用 text2image_prepare_images")
    storyboard_output = _load_saved_storyboard(image_metadata, cache_root, storyboard_text)
    shots = parse_storyboard(storyboard_output, tts_result["timeline"])
    images = image_manifest.get("images")
    expected_image_ids = {shot["id"] for shot in shots}
    if not isinstance(images, dict) or set(images) != expected_image_ids:
        raise WorkflowStepError(
            "Agent 生图清单没有完整覆盖所有镜头",
            {"expected_image_ids": sorted(expected_image_ids), "actual_image_ids": sorted(images or {})},
        )
    for image_id, image_path in images.items():
        if not Path(str(image_path)).resolve().is_file():
            raise WorkflowStepError(f"Agent 生图清单中的图片不存在：{image_id} -> {image_path}")
    for shot in shots:
        shot["image_path"] = str(Path(images[shot["id"]]).resolve())
    try:
        cover = generate_cover(
            [shot["image_path"] for shot in shots],
            metadata["title"],
            cache_root / "cover.png",
            size=line.video_size,
        )
    except CoverError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    cover_result = {"output_path": cover["output_path"]}

    forced = set(force_shot_ids or [])
    unknown_forced = forced.difference(shot["id"] for shot in shots)
    if unknown_forced:
        raise WorkflowStepError(f"要重做的镜头不存在：{sorted(unknown_forced)}")
    segment_dir = cache_root / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    first_shot = shots[0]
    first_segment = segment_dir / f"{first_shot['id']}.mp4"
    first_shot["cache_hit"] = _render_first_shot_cached(
        line,
        shots,
        first_shot,
        tts_path,
        first_segment,
        force=first_shot["id"] in forced,
    )
    video_shots = [{
        "id": first_shot["id"],
        "segment_path": str(first_segment),
        "subtitle": first_shot["subtitle"],
    }]
    video_shots.extend(
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
    )
    bgm = select_bgm(id=line.bgm_id)
    final_result = assemble_text2image_video(
        line,
        video_shots,
        cache_dir=cache_root / "shot-cache",
        output_dir=output_root,
        title=metadata["title"],
        cover_path=cover_result["output_path"],
        bgm_path=bgm["path"],
        force_shot_ids=[shot_id for shot_id in forced if shot_id != first_shot["id"]],
    )
    final_path = Path(final_result["output_path"])

    publish_copy = "【" + metadata["short_title"] + " " + " ".join(
        f"#{tag.lstrip('#')}" for tag in metadata["hashtags"]
    ) + "】"
    title_path = output_root / "title.txt"
    publish_copy_path = output_root / "publish-copy.txt"
    title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
    publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    manifest = {
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "line": line.id,
        "topic": record["topic"],
        "run_id": run_id,
        "article": article,
        **metadata,
        "cover_path": cover_result["output_path"],
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "matrixmedia_account_group": line.matrixmedia_account_group,
        "created_at": created_at,
        "topic_record_id": record["id"],
        "shots": shots,
    }
    manifest_path = cache_root / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
