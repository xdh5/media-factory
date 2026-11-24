"""从长视频原画面裁取财经竖版切片，保留贴图、字幕及运镜。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import unicodedata
from pathlib import Path

from tools.generate_subtitles import generate_subtitles
from tools.generate_subtitles._constants import SUBTITLE_FONT_DIRECTORY


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")


def _display_title(text: str) -> str:
    """标题显示遵循字幕规则，只保留顿号。"""
    return ''.join(char for char in text if char == '、' or not unicodedata.category(char).startswith('P'))


def produce_youtube_short(manifest: dict) -> dict:
    """直接复用长片成品画面与原声，只编码一次竖版布局。"""
    selection = manifest['youtube_short_selection']
    start_line, end_line = int(selection['start_line']), int(selection['end_line'])
    selected = [shot for shot in manifest['shots'] if any(start_line <= int(line[1:]) <= end_line for line in shot['line_ids'])]
    lines = selection['title_lines']
    if ''.join(lines) != manifest['title'] or len(lines) not in (1, 2):
        raise ValueError('Shorts标题须按完整长标题拆成一至两行')
    work = Path(manifest['cache_dir']) / 'youtube-short'
    work.mkdir(parents=True, exist_ok=True)
    output = Path(manifest['output_dir']) / 'youtube-short.mp4'
    start, end = selected[0]['audio_start'], selected[-1]['audio_end']
    duration = end - start
    cues = []
    for number, original in enumerate(lines):
        line = _display_title(original)
        cues.append({'start': 0, 'end': duration, 'text': line,
                     'style': {'font_size': min(80, 920 // len(line)), 'primary_color': '#FFFFFF' if number == 0 else '#FFE600'},
                     'position': {'alignment': 5, 'x': 540, 'y': 310 + number * 100}})
    ass = work / 'fixed-title.ass'
    generate_subtitles(cues, ass, 1080, 1920, style={'bold': True, 'outline': 3, 'canvas_width_ratio': 0.9})
    graph = ('[0:v]split=2[main][bg];'
             '[main]scale=1080:608,setsar=1[foreground];'
             '[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,'
             'boxblur=12:2,eq=brightness=-0.20,scale=1080:1920[background];'
             '[background][foreground]overlay=0:600,'
             'drawbox=x=0:y=200:w=1080:h=260:color=black@0.35:t=fill,'
             f"subtitles='{_filter_path(ass)}':fontsdir='{_filter_path(SUBTITLE_FONT_DIRECTORY)}'[out]")
    source = Path(manifest['video_path'])
    signature = hashlib.sha256((json.dumps(selection, sort_keys=True, ensure_ascii=False) + graph + ass.read_text(encoding='utf-8') + str(source.stat().st_mtime_ns)).encode()).hexdigest()
    stamp = work / 'video.signature'
    if not output.is_file() or not stamp.is_file() or stamp.read_text() != signature:
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-filter_complex_threads', '1',
                        '-ss', str(start), '-t', str(duration), '-i', str(source), '-filter_complex', graph,
                        '-map', '[out]', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21',
                        '-pix_fmt', 'yuv420p', '-threads', '4', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(output)], check=True)
        stamp.write_text(signature)
    description = Path(manifest['output_dir']) / 'youtube-description.txt'
    description.write_text(manifest['youtube_description'].rstrip() + '\n\n' + ' '.join('#' + tag.lstrip('#') for tag in manifest['youtube_hashtags']) + '\n', encoding='utf-8')
    return {'youtube_short_path': str(output), 'youtube_short_shot_ids': [shot['id'] for shot in selected],
            'youtube_short_source_start': start, 'youtube_short_source_end': end, 'youtube_description_path': str(description)}
