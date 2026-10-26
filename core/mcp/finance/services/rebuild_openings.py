"""按原生产清单重制首幕，复用原配音和正文画面，不重新领取稿件。"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess

from core.tools.generate_final_video import generate_final_video
from core.tools.generate_final_video._ffmpeg import _executable, _probe, _run
from core.tools.generate_stock_video import download_stock_video, prepare_stock_clip
from core.tools.generate_stock_video.generate_stock_video import _best_variant, _request_json
from core.tools.media_files import download_public_file
from core.tools.media_records import list_production_outputs
from core.tools.publish_media.local_assets import local_video_path, r2_object_key
from ..config.settings import VIDEO_SIZE, PROJECT_CACHE_ROOT
from ..errors import WorkflowStepError
from .production_config import _production_config
from .upload_to_r2 import upload_finance_assets_to_r2
from .video_layers import _hook_layer, _hook_title_lines_override, _split_title_parts, _with_display_text
from .video_opening import _render_first_shot_cached

LAYOUT_REVISION = 2


def _audio_hash(path: Path) -> str:
    result = subprocess.run(
        [_executable("ffmpeg"), "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
         "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return result.stdout.strip()


def _preview(video: Path, output: Path) -> None:
    _run([_executable("ffmpeg"), "-y", "-ss", "1.4", "-i", str(video), "-frames:v", "1", str(output)],
         "提取首幕检查图", timeout_seconds=90)


def _rebuild_one(record: dict, lines: list[str] | None, config: dict, video_config: dict, progress) -> dict:
    part = int(record.get("content_part") or 1)
    run_dir = record["run_id"] + (f"-part{part}" if part > 1 else "")
    cache = PROJECT_CACHE_ROOT / "finance" / "rebuild-openings" / run_dir
    cache.mkdir(parents=True, exist_ok=True)
    progress(f"恢复原生产清单：{run_dir}")
    manifest_path = cache / "manifest.json"
    download_public_file(f"runs/finance/{run_dir}/manifest.json", manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    title_lines = _hook_title_lines_override(lines) if lines is not None else _split_title_parts(manifest["short_title"])
    if "".join(title_lines) != "".join(_split_title_parts(manifest["short_title"])):
        raise WorkflowStepError("首幕语义分行必须完整保留原短标题，不能增删文字")
    signature = hashlib.sha256(json.dumps([LAYOUT_REVISION, title_lines], ensure_ascii=False).encode()).hexdigest()
    source = local_video_path(record)
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        progress(f"恢复原成片：{run_dir}")
        download_public_file(r2_object_key(record), source)
    preview = cache / "opening-preview.png"
    if (manifest.get("opening_rebuild") or {}).get("signature") == signature:
        _preview(source, preview)
        return {"title": manifest["title"], "video_path": str(source), "preview_path": str(preview),
                "video_url": record["r2_url"], "hook_title_lines": title_lines, "cache_hit": True}

    output = source.parent
    for field in ("cover_path", "title_path", "short_title_path", "publish_copy_path", "source_hook_path", "attribution_comment_path"):
        value = manifest.get(field)
        if value:
            filename = str(value).replace("\\", "/").rsplit("/", 1)[-1]
            destination = output / filename
            download_public_file(f"runs/finance/{run_dir}/{filename}", destination)
            manifest[field] = str(destination)
    first = deepcopy(manifest["shots"][0])
    attributions = [item for item in manifest["stock_video_attributions"] if item["video_id"] == first["id"]]
    if not attributions or any(item["provider"] != "pexels" for item in attributions):
        raise WorkflowStepError("首幕重制需要清单中可精确恢复的 Pexels 原素材，不自动换片")
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise WorkflowStepError("缺少 PEXELS_API_KEY，无法恢复首幕原素材")
    raw_sources = []
    for item in attributions:
        progress(f"恢复首幕原素材：{run_dir} / {item['source_id']}")
        video = _request_json(f"https://api.pexels.com/v1/videos/videos/{item['source_id']}", headers={"Authorization": api_key})
        variant = _best_variant([{**row, "url": row["link"]} for row in video["video_files"]
                                 if row.get("file_type") == "video/mp4"], "landscape")
        if variant is None:
            raise WorkflowStepError(f"原素材没有可用 MP4：{item['source_id']}")
        raw = cache / f"raw-{item['source_id']}.mp4"
        download_stock_video({"provider": "pexels", "download_url": variant["url"]}, raw)
        raw_sources.append(raw)
    clip, frame = cache / "stock-clip.mp4", cache / "stock-frame.png"
    prepare_stock_clip(raw_sources, clip, first["duration"], size=VIDEO_SIZE,
                       frame_path=frame, soft_blur_sigma=float(video_config["soft_blur_sigma"]))
    first.update(intro_video_path=str(clip), image_path=str(frame), frame_path=str(frame))
    clean_opening = cache / "clean-opening.mp4"
    settings = _production_config({**config, "hook_title_lines": title_lines})
    progress(f"重制首幕排版：{run_dir}")
    _render_first_shot_cached(settings["intro"], settings["intro_sfx_path"], [first], first, clean_opening, force=True)
    first["segment_path"] = str(clean_opening)
    hook_layers = _hook_layer([first], settings, manifest, manifest.get("source_hook", ""), cache)
    opening = cache / "opening.mp4"
    generate_final_video(
        _with_display_text([first]), opening, cache / "opening-render", size=VIDEO_SIZE,
        tts_path=source, cover_path=manifest["cover_path"], cover_duration=settings["cover_frame_seconds"],
        stickers=list(settings["shot_stickers"]), subtitle_style=settings["subtitle_style"],
        subtitle_position=settings["subtitle_position"], extra_ass_paths=hook_layers,
        emphasis_lines={"enabled": False}, secondary_subtitles={"enabled": False},
    )
    cut = float(_probe(clean_opening)["duration"])
    rebuilt = cache / source.name
    filters = (f"[0:v]trim=duration={cut:.9f},setpts=PTS-STARTPTS[head];"
               f"[1:v]trim=start={cut:.9f},setpts=PTS-STARTPTS[body];[head][body]concat=n=2:v=1:a=0[video]")
    progress(f"合回正文并保留原音轨：{run_dir}")
    _run([_executable("ffmpeg"), "-y", "-filter_complex_threads", "2", "-i", str(opening), "-i", str(source),
          "-filter_complex", filters, "-map", "[video]", "-map", "1:a:0", "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "18", "-threads", "2", "-r", "30", "-pix_fmt", "yuv420p",
          "-c:a", "copy", "-movflags", "+faststart", str(rebuilt)], "合成重制成片", timeout_seconds=3600)
    before, after = float(_probe(source)["duration"]), float(_probe(rebuilt)["duration"])
    original_audio = _audio_hash(source)
    if abs(before - after) > 0.08 or original_audio != _audio_hash(rebuilt):
        raise WorkflowStepError("重制后时长或音轨与原成片不一致，不交付、不替换产物")
    _preview(rebuilt, preview)
    rebuilt.replace(source)
    manifest.update(video_path=str(source), output_dir=str(output), cache_dir=str(cache), manifest_path=str(manifest_path),
                    video_revision=f"opening-v2-{signature[:10]}", opening_rebuild={
                        "signature": signature, "revision": LAYOUT_REVISION, "hook_title_lines": title_lines,
                        "original_audio_hash": original_audio, "duration_before": before, "duration_after": after,
                    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(f"交付重制成片到 R2：{run_dir}")
    uploaded = upload_finance_assets_to_r2(manifest_path)
    return {"title": manifest["title"], "video_path": str(source), "preview_path": str(preview),
            "video_url": uploaded["video_url"], "hook_title_lines": title_lines, "audio_preserved": True}


def rebuild_finance_openings(publish_date: str, title_lines_by_part: dict, production_config: dict,
                             video_config: dict, progress=None) -> dict:
    report = progress or (lambda message: None)
    records = list_production_outputs(business_line="finance", publish_date=publish_date, source="local_mcp")
    if not records:
        raise WorkflowStepError(f"{publish_date} 没有可重制的原成片，不另选稿件")
    results = [_rebuild_one(record, title_lines_by_part.get(str(record["content_part"])),
                            production_config, video_config, report)
               for record in sorted(records, key=lambda row: int(row["content_part"]))]
    return {"publish_date": publish_date, "status": "succeeded", "videos": results, "published": False}
