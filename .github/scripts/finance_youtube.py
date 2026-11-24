"""财经 YouTube 账号检查与长短视频独立发布入口。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.database.publication_records import list_publication_records
from tools.publish_media.accounts import resolve_account_group
from tools.publish_media.concurrency import publication_lock_keys, publication_slot
from tools.publish_media.content import local_publish_items
from tools.publish_media.publisher import _publishing, _save_publication
from tools.r2_files import download_file


def check_youtube_account() -> list[dict]:
    """只核实财经YouTube原频道的真实授权，不上传内容。"""
    return resolve_account_group('finance', 'finance', ['youtube'])


async def check_accounts(publish_date: str) -> dict:
    routes = await asyncio.to_thread(check_youtube_account)
    return {'status': 'ready', 'publish_date': publish_date, 'accounts': [row['platform_account_id'] for row in routes]}


def _publish_day(publish_date: str, variant: str) -> dict:
    route = check_youtube_account()[0]
    print('**全部账号已登录，开始发布**', flush=True)
    items = local_publish_items('finance', publish_date, content_kind='finance')
    publish_batch, _, _ = _publishing()
    output = {'published': [], 'skipped': [], 'failed': []}
    for item in items:
        publication_id = f"{item['production_id']}:youtube-{variant}"
        with publication_slot(publication_lock_keys(route)):
            records = list_publication_records(business_line='finance', platform='youtube', run_id=item['run_id'])
            known_ids = {publication_id, item['production_id']} if variant == 'long' else {publication_id}
            if any(row['publication_id'] in known_ids and row['account_id'] == route['platform_account_id'] for row in records):
                output['skipped'].append(publication_id)
                continue
            folder = Path(item['local_path']).parent
            part = int(item['content_part'])
            directory = item['run_id'] if part == 1 else f"{item['run_id']}-part{part}"
            prefix = f'runs/finance/{directory}'
            metadata_path = folder / 'youtube-publication-manifest.json'
            download_file(f'{prefix}/manifest.json', metadata_path)
            manifest = json.loads(metadata_path.read_text(encoding='utf-8'))
            description = manifest['youtube_description'].rstrip() + '\n\n' + ' '.join('#' + tag.lstrip('#') for tag in manifest['youtube_hashtags'])
            video = Path(item['local_path']) if variant == 'long' else folder / 'youtube-short.mp4'
            if variant == 'short' and not video.is_file():
                download_file(f'{prefix}/youtube-short.mp4', video)
            cover = str(folder / 'cover-widescreen.png') if variant == 'long' else ''
            scheduled_at = f"{publish_date}T{'14' if part == 1 else '18'}:00:00+08:00"
            future = datetime.fromisoformat(scheduled_at) > datetime.now(ZoneInfo('Asia/Shanghai'))
            result = publish_batch({'account_group': 'finance', 'publish_mode': 'scheduled' if future else 'immediate',
                                    'publish_at': scheduled_at if future else 'now',
                                    'targets': [{'platform': 'youtube', 'account_key': route['account_key'],
                                                 'title': manifest['title'], 'description': description,
                                                 'file': str(video), 'thumbnail_path': cover,
                                                 'publication_id': publication_id, 'client_ref': publication_id}]},
                                   account_routes={route['account_key']: route})
            if result['failed']:
                output['failed'].extend(result['failed'])
                continue
            sent = result['published'][0]
            saved = _save_publication({'item': {**item, 'production_id': publication_id}, 'route': route}, sent, 'finance')
            receipt = folder / f'youtube-{variant}-publication.json'
            receipt.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
            output['published'].append(saved)
    if output['failed']:
        raise RuntimeError(f"YouTube {variant}发布失败：{output['failed']}")
    return output


async def publish_day(publish_date: str, variant: str) -> dict:
    return await asyncio.to_thread(_publish_day, publish_date, variant)
