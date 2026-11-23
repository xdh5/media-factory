"""Azure Neural 与 HD Flash 配音，按模型支持范围组装 SSML。"""

import os
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import requests
from dotenv import load_dotenv

from ._pipeline import synthesize_pipeline


def generate_tts_azure(script: list[dict], output_path: str | Path, *, rate: str = '+0%') -> dict:
    """按原稿逐行合成，字幕分页不影响句内表达。"""
    load_dotenv()
    key = os.environ['AZURE_SPEECH_KEY']
    region = os.environ['AZURE_SPEECH_REGION']

    def speak(line: dict, raw_path: Path):
        text = line.get('ssml', escape(line['text']))
        voice = line['voice'].removeprefix('azure:')
        flash = ':DragonHDFlash' in voice
        if not flash:
            text = f'<prosody rate={quoteattr(rate)}>{text}</prosody>'
        ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
                f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">'
                f'<voice name={quoteattr(voice)}>{text}</voice></speak>')
        response = requests.post(f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1',
            headers={'Ocp-Apim-Subscription-Key': key, 'Content-Type': 'application/ssml+xml',
                     'X-Microsoft-OutputFormat': 'riff-24khz-16bit-mono-pcm'},
            data=ssml.encode('utf-8'), timeout=60)
        response.raise_for_status()
        raw_path.write_bytes(response.content)

    return synthesize_pipeline(script, speak, Path(output_path),
                               concurrency=2, provider='azure')
