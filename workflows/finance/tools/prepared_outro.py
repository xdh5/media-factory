"""随生产包分发的固定片尾与原始配音。"""
import json
import wave
from pathlib import Path
from tools.resources import package_resource_path


def outro_resources() -> dict:
    root = package_resource_path('workflows', 'finance', 'resources')
    metadata = json.loads((root / 'goose-outro-prepared.json').read_text(encoding='utf-8'))
    return {**metadata, 'video': root / 'goose-outro-prepared.mp4', 'audio': root / 'goose-outro-narration.wav'}


def append_outro(result: dict, text: str, voice: str, rate: str) -> dict:
    """正文只合成一次，原样追加预制片尾配音并补齐时间轴。"""
    resources = outro_resources()
    if (text, voice, rate) != (resources['text'], resources['voice'], resources['rate']):
        raise ValueError('结束语、音色或语速与预制片尾不一致，请重新制作预制片尾资源')
    output = Path(result['output_path'])
    with wave.open(str(output), 'rb') as body:
        parameters = body.getparams()
        body_audio = body.readframes(body.getnframes())
    with wave.open(str(resources['audio']), 'rb') as ending:
        ending_audio = ending.readframes(ending.getnframes())
        duration = ending.getnframes() / ending.getframerate()
    with wave.open(str(output), 'wb') as target:
        target.setparams(parameters)
        target.writeframes(body_audio)
        target.writeframes(ending_audio)
    start = result['total_duration']
    result['timeline'].append({'id': f'L{len(result["timeline"]) + 1:03d}', 'text': text,
                               'voice': voice, 'start': start, 'end': round(start + duration, 6),
                               'duration': duration})
    result['line_count'] += 1
    result['total_duration'] = round(start + duration, 6)
    return result
