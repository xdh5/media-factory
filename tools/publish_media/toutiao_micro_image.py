"""发布业务为微头条指定配图，重试复用已保存的选择。"""

import json
from pathlib import Path
import random


def select_toutiao_micro_image(manifest: dict) -> str:
    output = Path(manifest['output_dir'])
    selection_path = output / 'toutiao-micro-image.json'
    if selection_path.is_file():
        filename = json.loads(selection_path.read_text(encoding='utf-8'))['image_filename']
    else:
        images = [Path(manifest[f'article_image_{index}_path']).name for index in (1, 2, 3)]
        filename = random.choice(images)
        selection_path.write_text(json.dumps({'image_filename': filename}, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(output / filename)
