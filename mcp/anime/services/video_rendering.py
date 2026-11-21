"""按来源编码参数选择拼接、边界裁切或转码方案。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


from .._constants import SEGMENTATION_DURATION, SEGMENTATION_EPISODES
from .._errors import AnimeError

from .ffmpeg import Progress, media_executable, probe_video, report_progress, run_ffmpeg, subprocess_options


# 关键帧裁切允许的时间偏差；超出才转码这一段。
_SPLIT_TOLERANCE_SECONDS = 10.0


def _render_split(clips: list[dict], output_path: Path, *, progress: Progress | None, label: str) -> None:
    """按时间线无损裁切长视频；关键帧偏差过大时才转码这一段，避免整部重编码。"""
    if len(clips) == 1 and clips[0]["full"]:
        shutil.copy2(clips[0]["path"], output_path)
        return
    try:
        _concat_packet_copy(clips, output_path,
                            tolerance=max(_SPLIT_TOLERANCE_SECONDS, len(clips) * 0.5))
    except AnimeError:
        report_progress(progress, f"{label} 关键帧裁切时长偏差过大，改为转码这一段")
        _concat_reencode(clips, output_path, progress=progress, label=label)


def render_video_part(clips: list[dict], output_path: Path, *, progress: Progress | None, label: str,
                 segmentation: str = SEGMENTATION_EPISODES) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.tmp.mp4")
    try:
        if segmentation == SEGMENTATION_DURATION:
            _render_split(clips, temporary, progress=progress, label=label)
        elif len(clips) == 1 and clips[0]["full"]:
            shutil.copy2(clips[0]["path"], temporary)
        elif _can_stream_copy(clips):
            try:
                _concat_copy(clips, temporary)
            except AnimeError:
                report_progress(progress, f"{label} 直接拼接失败，仅转换不兼容来源")
                _concat_hybrid(clips, temporary, progress=progress, label=label)
        elif clips and all(_signature(clip["probe"]) == _signature(clips[0]["probe"]) for clip in clips):
            try:
                _concat_trimmed_boundaries(clips, temporary, progress=progress, label=label)
            except AnimeError:
                report_progress(progress, f"{label} 边界处理后格式不一致，仅转换不兼容来源")
                _concat_hybrid(clips, temporary, progress=progress, label=label)
        else:
            report_progress(progress, f"{label} 来源参数不一致，统一音频后拼接，兼容的视频不重新编码")
            _concat_hybrid(clips, temporary, progress=progress, label=label)
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise AnimeError(f"{label} 没有写出视频文件")
        try:
            validate_audio(temporary)
        except AnimeError:
            if len(clips) == 1:
                raise
            report_progress(progress, f"{label} 直接拼接音轨解码失败，分别统一来源音频后重试")
            _concat_hybrid(clips, temporary, progress=progress, label=label)
            validate_audio(temporary)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)


def _can_stream_copy(clips: list[dict]) -> bool:
    if not clips or any(not clip["full"] for clip in clips):
        return False
    first = _signature(clips[0]["probe"])
    return all(_signature(clip["probe"]) == first for clip in clips)


def _concat_trimmed_boundaries(clips, output_path, *, progress, label):
    """完整块直接复用，只编码分段边界涉及的小块，避免整段长视频重复编码。"""
    with tempfile.TemporaryDirectory(prefix=".boundary-", dir=output_path.parent) as temporary:
        prepared = []
        signature = _signature(clips[0]["probe"])
        for index, clip in enumerate(clips):
            if clip["full"]:
                prepared.append(clip)
                continue
            report_progress(progress, f"{label} 仅处理分段边界 {index + 1}/{len(clips)}")
            path = Path(temporary) / f"boundary-{index}.mp4"
            _concat_reencode([clip], path, progress=progress, label=label)
            probe = probe_video(path)
            if _signature(probe) != signature or abs(probe["duration"] - clip["duration"]) > 0.5:
                raise AnimeError("边界视频的格式或时长不适合直接拼接")
            prepared.append({"path": path, "probe": probe, "duration": probe["duration"], "full": True})
        _concat_copy(prepared, output_path)
        expected = sum(clip["duration"] for clip in clips)
        if abs(probe_video(output_path)["duration"] - expected) > max(0.5, len(clips) * 0.05):
            raise AnimeError("边界处理后的成片时长不符")


def _concat_packet_copy(clips: list[dict], output_path: Path, tolerance: float | None = None) -> None:
    """不解码音视频；只对分段边界做关键帧裁切，再按原始数据包拼接。"""
    ffmpeg = media_executable("ffmpeg")
    with tempfile.TemporaryDirectory(prefix=".packet-copy-", dir=output_path.parent) as temporary:
        prepared: list[dict] = []
        for index, clip in enumerate(clips):
            if clip["full"]:
                prepared.append(clip)
                continue
            path = Path(temporary) / f"boundary-{index}.mp4"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if clip["start"] > 0.05:
                command.extend(["-ss", f"{clip['start']:.3f}"])
            command.extend([
                "-i", str(clip["path"]), "-t", f"{clip['duration']:.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(path),
            ])
            run_ffmpeg(command, total_seconds=clip["duration"], progress=None, label="边界直接裁切")
            probe = probe_video(path)
            prepared.append({"path": path, "probe": probe, "duration": probe["duration"], "full": True})
        _concat_copy(prepared, output_path)
        expected = sum(clip["duration"] for clip in clips)
        actual = probe_video(output_path)["duration"]
        if abs(actual - expected) > (max(3.0, len(clips) * 0.1) if tolerance is None else tolerance):
            raise AnimeError("直接拼接后的成片时长不符")


def _concat_hybrid(
    clips: list[dict],
    output_path: Path,
    *,
    progress: Progress | None,
    label: str,
) -> None:
    """复用主流格式原片，只转换格式不同或需要精确裁切的少数来源。"""
    signatures = [_signature(clip["probe"]) for clip in clips]
    target_signature = Counter(signatures).most_common(1)[0][0]
    target_probe = next(clip["probe"] for clip in clips if _signature(clip["probe"]) == target_signature)
    if target_probe.get("vcodec") != "h264" or target_probe.get("acodec") != "aac":
        raise AnimeError("主流来源不是 H.264/AAC，无法局部统一后直接拼接")
    width = _even(int(target_probe.get("width") or 0))
    height = _even(int(target_probe.get("height") or 0))
    fps_token = str(target_probe.get("fps_token") or "30")
    sample_rate = int(target_probe.get("sample_rate") or 48000)
    channels = int(target_probe.get("channels") or 2)
    pixel_format = str(target_probe.get("pix_fmt") or "yuv420p")
    if width < 2 or height < 2:
        raise AnimeError("主流来源没有可用画面")

    with tempfile.TemporaryDirectory(prefix=".hybrid-", dir=output_path.parent) as temporary:
        prepared: list[dict] = []
        remuxed = 0
        converted = 0
        for index, clip in enumerate(clips, start=1):
            if clip["full"] and _video_signature(clip["probe"]) == _video_signature(target_probe):
                path = Path(temporary) / f"{index:03d}-remux.mp4"
                try:
                    _normalize_audio_clip(clip, path, sample_rate, channels)
                    probe = probe_video(path)
                    remuxed += 1
                    prepared.append(
                        {"path": path, "probe": probe, "duration": probe["duration"], "full": True}
                    )
                    continue
                except AnimeError:
                    path.unlink(missing_ok=True)
                    report_progress(progress, f"{label} 第 {index}/{len(clips)} 条无损整理失败，仅转换这一条")
            else:
                report_progress(progress, f"{label} 仅转换第 {index}/{len(clips)} 条不兼容来源")
            converted += 1
            path = Path(temporary) / f"{index:03d}-normalized.mp4"
            _normalize_clip(
                clip, path, width=width, height=height, fps_token=fps_token,
                pixel_format=pixel_format, sample_rate=sample_rate, channels=channels,
                progress=progress, label=label,
            )
            probe = probe_video(path)
            prepared.append({"path": path, "probe": probe, "duration": probe["duration"], "full": True})
        report_progress(progress, f"{label} 复用视频并统一音频 {remuxed} 条，转换视频 {converted} 条")
        # ffprobe 的平均帧率等字段可能因重置时间戳而换一种等价值表示。
        # 以实际无损拼接和最终时长为准，不能在拼接前按字符串签名误判。
        _concat_copy(prepared, output_path)
        expected = sum(clip["duration"] for clip in clips)
        if abs(probe_video(output_path)["duration"] - expected) > max(1.0, len(clips) * 0.05):
            raise AnimeError("局部转换后的成片时长不符")


def _remux_clip(clip: dict, output_path: Path) -> None:
    """不解码音视频，丢弃损坏数据包并重置单条来源的时间戳。"""
    ffmpeg = media_executable("ffmpeg")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-fflags", "+discardcorrupt", "-err_detect", "ignore_err",
        "-i", str(clip["path"]),
        "-map", f"0:{int(clip['probe']['video_stream_index'])}",
    ]
    audio_index = clip["probe"].get("audio_stream_index")
    if audio_index is not None:
        command.extend(["-map", f"0:{int(audio_index)}"])
    command.extend([
        "-c", "copy", "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart", str(output_path),
    ])
    run_ffmpeg(command, total_seconds=clip["duration"], progress=None, label="无损整理来源")


def _normalize_clip(
    clip: dict,
    output_path: Path,
    *,
    width: int,
    height: int,
    fps_token: str,
    pixel_format: str,
    sample_rate: int,
    channels: int,
    progress: Progress | None,
    label: str,
) -> None:
    """把单条不兼容来源转换为主流参数，其他来源不解码。"""
    ffmpeg = media_executable("ffmpeg")
    duration = f"{clip['duration']:.3f}"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if clip["start"] > 0.05:
        command.extend(["-ss", f"{clip['start']:.3f}"])
    if not clip["full"]:
        command.extend(["-t", duration])
    command.extend(["-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", str(clip["path"])])
    video_index = int(clip["probe"]["video_stream_index"])
    video_filter = (
        f"[0:{video_index}]setpts=PTS-STARTPTS,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps_token},format={pixel_format},"
        f"trim=duration={duration},setpts=PTS-STARTPTS[vout]"
    )
    layout = "mono" if channels == 1 else "stereo"
    audio_index = clip["probe"].get("audio_stream_index")
    if audio_index is None:
        audio_filter = (
            f"anullsrc=channel_layout={layout}:sample_rate={sample_rate},"
            f"atrim=duration={duration},asetpts=PTS-STARTPTS[aout]"
        )
    else:
        audio_filter = (
            f"[0:{int(audio_index)}]asetpts=PTS-STARTPTS,"
            f"aresample={sample_rate}:async=1:first_pts=0,"
            f"aformat=sample_fmts=fltp:channel_layouts={layout},"
            f"atrim=duration={duration},asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={duration}[aout]"
        )
    command.extend([
        "-filter_complex", f"{video_filter};{audio_filter}",
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", fps_token, "-fps_mode", "cfr",
        "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate), "-ac", str(channels),
        "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output_path),
    ])
    run_ffmpeg(command, total_seconds=clip["duration"], progress=progress, label=label)


def _signature(probe: dict) -> tuple:
    return (
        probe.get("width"),
        probe.get("height"),
        probe.get("vcodec"),
        probe.get("acodec"),
        probe.get("fps_token"),
        probe.get("pix_fmt"),
        probe.get("sample_rate"),
        probe.get("channels"),
        probe.get("audio_extradata_hash"),
    )


def _video_signature(probe):
    return tuple(probe.get(key) for key in ("width", "height", "vcodec", "fps_token", "pix_fmt"))


def _normalize_audio_clip(clip, output_path, sample_rate, channels):
    """在各来源自己的音频配置下解码，再编码成一致的 AAC，视频保持原样。"""
    command = [media_executable("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-xerror",
               "-i", str(clip["path"]), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
               "-c:a", "aac", "-profile:a", "aac_low", "-ar", str(sample_rate), "-ac", str(channels),
               "-b:a", "192k", "-af", "aresample=async=1:first_pts=0",
               "-movflags", "+faststart", str(output_path)]
    run_ffmpeg(command, total_seconds=clip["duration"], progress=None, label="统一来源音频")


def validate_audio(path):
    """完整解码音轨，阻止时长正常但 AAC 数据损坏的视频进入检查点或上传。"""
    probe = probe_video(Path(path))
    if probe.get("audio_stream_index") is None:
        return
    log = Path(path).with_suffix(".audio-check.log")
    command = [media_executable("ffmpeg"), "-nostdin", "-v", "error", "-xerror", "-i", str(path),
               "-map", "0:a:0", "-vn", "-f", "null", "-"]
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=stream,
                                timeout=max(600, probe["duration"]), **subprocess_options())
    if result.returncode:
        detail = log.read_text(encoding="utf-8", errors="replace")[-1200:]
        raise AnimeError("视频音轨完整解码失败，不能上传或用作检查点", {"file": Path(path).name, "audio_error": detail})
    log.unlink(missing_ok=True)


def _concat_copy(clips: list[dict], output_path: Path) -> None:
    ffmpeg = media_executable("ffmpeg")
    script = output_path.with_name(f".{output_path.stem}.concat.txt")
    lines = []
    for clip in clips:
        escaped = clip["path"].resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(script),
        "-c", "copy", "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        run_ffmpeg(command, total_seconds=sum(clip["duration"] for clip in clips), progress=None, label="直接拼接")
    finally:
        script.unlink(missing_ok=True)


def _concat_reencode(
    clips: list[dict],
    output_path: Path,
    *,
    progress: Progress | None,
    label: str,
) -> None:
    ffmpeg = media_executable("ffmpeg")
    canvas = clips[0]["probe"]
    width = _even(int(canvas.get("width") or 0))
    height = _even(int(canvas.get("height") or 0))
    if width < 2 or height < 2:
        raise AnimeError("视频没有可用画面，无法拼接")
    fps_token = _shared_fps(clips)
    filters: list[str] = []
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for index, clip in enumerate(clips):
        if clip["start"] > 0.05:
            command.extend(["-ss", f"{clip['start']:.3f}"])
        if not clip["full"]:
            command.extend(["-t", f"{clip['duration']:.3f}"])
        # 来源文件可能夹有少量损坏 AAC 包；保留可解码原声，仅跳过坏包。
        command.extend(["-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", str(clip["path"])])
        duration = f"{clip['duration']:.3f}"
        video_index = int(clip["probe"]["video_stream_index"])
        filters.append(
            f"[{index}:{video_index}]setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps_token},format=yuv420p,"
            f"trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
        )
        audio_index = clip["probe"].get("audio_stream_index")
        if audio_index is None:
            filters.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filters.append(
                f"[{index}:{int(audio_index)}]asetpts=PTS-STARTPTS,"
                f"aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS,apad=whole_dur={duration}[a{index}]"
            )
    joined = "".join(f"[v{index}][a{index}]" for index in range(len(clips)))
    filters.append(f"{joined}concat=n={len(clips)}:v=1:a=1[vout][aout]")
    graph = ";".join(filters)
    command.extend([
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", fps_token, "-fps_mode", "cfr",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(output_path),
    ])
    total_seconds = sum(clip["duration"] for clip in clips)
    # Windows 命令行大约 3 万字符。超长时改成逐段编码再复制拼接。
    if sum(len(part) + 1 for part in command) > 28000:
        _concat_reencode_chunked(
            clips, output_path, width=width, height=height, fps_token=fps_token,
            progress=progress, label=label,
        )
        return
    run_ffmpeg(command, total_seconds=total_seconds, progress=progress, label=label)


def _concat_reencode_chunked(
    clips: list[dict],
    output_path: Path,
    *,
    width: int,
    height: int,
    fps_token: str,
    progress: Progress | None,
    label: str,
) -> None:
    """滤镜图放不进命令行时，先把每条规范成相同参数，再复制拼接。"""
    ffmpeg = media_executable("ffmpeg")
    temporary_dir = output_path.parent / f".{output_path.stem}-parts"
    temporary_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[dict] = []
    try:
        for index, clip in enumerate(clips, start=1):
            report_progress(progress, f"正在编码{label}的第 {index}/{len(clips)} 条")
            target = temporary_dir / f"{index:03d}.mp4"
            duration = f"{clip['duration']:.3f}"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if clip["start"] > 0.05:
                command.extend(["-ss", f"{clip['start']:.3f}"])
            if not clip["full"]:
                command.extend(["-t", duration])
            # 与整段编码保持一致：只丢弃损坏包，不静音整条来源。
            command.extend(["-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", str(clip["path"])])
            video_index = int(clip["probe"]["video_stream_index"])
            video_filter = (
                f"[0:{video_index}]setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={fps_token},format=yuv420p,"
                f"trim=duration={duration},setpts=PTS-STARTPTS[vout]"
            )
            audio_index = clip["probe"].get("audio_stream_index")
            if audio_index is None:
                audio_filter = (
                    f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                    f"atrim=duration={duration},asetpts=PTS-STARTPTS[aout]"
                )
            else:
                audio_filter = (
                    f"[0:{int(audio_index)}]asetpts=PTS-STARTPTS,"
                    f"aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={duration},asetpts=PTS-STARTPTS,apad=whole_dur={duration}[aout]"
                )
            command.extend([
                "-filter_complex", f"{video_filter};{audio_filter}",
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-progress", "pipe:1", "-nostats",
                str(target),
            ])
            run_ffmpeg(command, total_seconds=clip["duration"], progress=progress, label=label)
            normalized.append({"path": target, "duration": clip["duration"], "full": True})
        _concat_copy(normalized, output_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _shared_fps(clips: list[dict]) -> str:
    tokens = [str(clip["probe"].get("fps_token") or "") for clip in clips]
    first = tokens[0]
    if first and first not in {"0/0", "0"} and all(token == first for token in tokens):
        return first
    return "30"


def _even(value: int) -> int:
    if value < 2:
        return 0
    return value if value % 2 == 0 else value + 1
