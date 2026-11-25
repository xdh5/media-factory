"""财经头条三类内容的素材恢复、独立去重、提交和入库。"""

from datetime import datetime
import json
from pathlib import Path

from tools.database.publication_records import list_publication_records
from tools.r2_files import download_file
from .publisher import preview_publication, publish_local_outputs, _save_publication


def publish_finance_toutiao_contents(publish_date: str, account_group: str, production_id: str,
                                    content_types: list[str], progress) -> dict:
    from publishing.runner import run_browser_publish

    preview = preview_publication('finance', publish_date, account_group, ['toutiao'],
                                  content_kind='finance', production_id=production_id)
    task = preview['tasks'][0]
    item = task['item']
    output = Path(item['local_path']).parent
    manifest_path = output / 'toutiao-publication-manifest.json'
    progress('恢复本期头条定稿及预制插图')
    part = int(item.get('content_part') or 1)
    directory = item['run_id'] + (f'-part{part}' if part > 1 else '')
    download_file(f'runs/finance/{directory}/manifest.json', manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update(output_dir=str(output), video_path=item['local_path'], cover_path=item['cover_path'],
                    widescreen_cover_path=item['widescreen_cover_path'])
    if {'article', 'micro'} & set(content_types):
        for field in ['toutiao_article_path', 'article_path', 'micro_summary_path',
                      'article_image_1_path', 'article_image_2_path', 'article_image_3_path']:
            filename = Path(manifest[field]).name
            destination = output / filename
            if not destination.is_file():
                download_file(f'runs/finance/{directory}/{filename}', destination)
            manifest[field] = str(destination)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    records = list_publication_records(business_line='finance', platform='toutiao', run_id=item['run_id'])
    result = {'published': [], 'skipped': [], 'failed': []}
    for kind in content_types:
        publication_id = production_id + (f':toutiao-{kind}' if kind != 'video' else '')
        if any(row['publication_id'] == publication_id and row['account_id'] == task['route']['platform_account_id'] for row in records):
            result['skipped'].append({'kind': kind, 'publication_id': publication_id})
            continue
        progress(f'头条{kind}：提交并等待接口回执，成功后独立入库')
        try:
            if kind == 'video':
                sent = publish_local_outputs('finance', publish_date, account_group, ['toutiao'],
                                             'immediate', 'now', content_kind='finance',
                                             production_id=production_id, progress=progress)
                result['published'].extend(sent['published'])
            else:
                receipt = run_browser_publish([f'publish-toutiao-{kind}', '--phone',
                                               task['route']['account_ref'], '--file', str(manifest_path)])
                saved = _save_publication({'item': {**item, 'production_id': publication_id}, 'route': task['route']},
                                         {'result': receipt, 'publish_mode': 'immediate',
                                          'publish_at': datetime.now().astimezone().isoformat()}, 'finance')
                result['published'].append(saved)
        except Exception as error:
            result['failed'].append({'kind': kind, 'message': str(error)})
            progress(f'头条{kind}失败：{error}')
    return result
