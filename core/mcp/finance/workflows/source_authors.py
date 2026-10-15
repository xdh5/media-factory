"""财经作者名单：查看、添加和删除。"""

from __future__ import annotations

from list_author_works import AuthorWorksError, resolve_author_profile
from ..infrastructure.source_scripts import (
    add_source_author,
    list_source_authors,
    remove_source_author,
)

from ..errors import WorkflowStepError
from .common import _map_error


def finance_list_source_authors() -> dict:
    """查看财经作者名单。按添加顺序返回主页、sec_user_id 和显示名。"""
    try:
        authors = list_source_authors()
    except Exception as extra:
        raise _map_error(extra) from extra
    return {"authors": authors, "author_count": len(authors)}


def finance_add_source_author(profile_url: str, display_name: str = "") -> dict:
    """添加一位财经作者。profile_url 可以是作者主页或「查看TA的更多作品」分享口令，display_name 是可选显示名。"""
    try:
        author = resolve_author_profile(profile_url)
        record = add_source_author(
            sec_user_id=author["sec_user_id"],
            profile_url=author["profile_url"],
            display_name=str(display_name or "").strip(),
        )
    except AuthorWorksError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    except Exception as extra:
        raise _map_error(extra) from extra
    return {"author": record}


def finance_remove_source_author(author: str) -> dict:
    """从财经作者名单删除一位作者。author 可以是主页链接或 sec_user_id。"""
    try:
        resolved = resolve_author_profile(author)
        record = remove_source_author(resolved["sec_user_id"])
    except AuthorWorksError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    except Exception as extra:
        raise _map_error(extra) from extra
    return {"author": record}
