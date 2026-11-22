"""从稿件登记的 R2 成图恢复财经封面，不重新生成或叠字。"""
from pathlib import Path
from tools.r2_files import download_file


def restore_cover_image(asset: dict, output_path: str | Path) -> dict:
    """生产环境只下载采集时完成的整张封面。"""
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    download_file(asset['key'], destination)
    return {'output_path': str(destination), 'r2_key': asset['key'],
            'title': asset['title'], 'short_title': asset['short_title']}
