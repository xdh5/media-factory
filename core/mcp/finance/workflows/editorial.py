"""财经未使用稿件的宿主定稿入口。"""

from ..services.editorial import list_editorial_drafts, save_editorial_drafts
from .common import _map_error


def finance_list_editorial_drafts(missing_only: bool = True) -> dict:
    """读取未使用的财经稿件，供宿主补齐定稿。"""
    try:
        return list_editorial_drafts(missing_only)
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_save_editorial_drafts(records: list[dict]) -> dict:
    """校验并保存宿主填写的正文、钩子、标题标签和封面定稿。"""
    try:
        return save_editorial_drafts(records)
    except Exception as exc:
        raise _map_error(exc) from exc
