"""删除一次生产的本地文件，保留话题去重记录。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ._constants import PROJECT_CACHE_ROOT, PROJECT_OUTPUT_ROOT, RUN_ID_PATTERN, WORKFLOW_ID_PATTERN
from ._errors import ConfirmationRequiredError, InvalidParameterError, RunDirectoryError

__all__ = ["clear_run"]


def _validated_ids(workflow: str, run_id: str) -> tuple[str, str]:
    wf = str(workflow or "").strip()
    rid = str(run_id or "").strip()
    if not re.fullmatch(WORKFLOW_ID_PATTERN, wf):
        raise InvalidParameterError("workflow", f"workflow 不合法：{workflow!r}")
    if not re.fullmatch(RUN_ID_PATTERN, rid):
        raise InvalidParameterError("run_id", f"run_id 必须是 run- 加至少 6 位数字，当前为 {run_id!r}")
    return wf, rid


def _run_subdir(root: Path, workflow: str, run_id: str) -> Path:
    root = root.resolve()
    target = (root / workflow / run_id).resolve()
    if target.parent != (root / workflow).resolve():
        raise InvalidParameterError("run_id", f"拒绝删除：路径不在标准目录下：{target}")
    if not str(target).startswith(str(root)):
        raise InvalidParameterError("run_id", f"拒绝删除：路径不在允许的根目录内：{target}")
    return target


def _delete_dir(target: Path) -> bool:
    if not target.exists():
        return False
    if not target.is_dir():
        raise RunDirectoryError(f"拒绝删除：目标不是目录：{target}")
    shutil.rmtree(target)
    leftover = target.parent
    if leftover.is_dir() and not any(leftover.iterdir()):
        leftover.rmdir()
    return True


def clear_run(workflow: str, run_id: str, *, confirmed: bool) -> dict:
    """删除 cache/{workflow}/{run_id} 与 outputs/{workflow}/{run_id}；不改话题库。"""
    if confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对删除本次生产文件的明确确认")
    wf, rid = _validated_ids(workflow, run_id)
    cache_dir = _run_subdir(PROJECT_CACHE_ROOT, wf, rid)
    output_dir = _run_subdir(PROJECT_OUTPUT_ROOT, wf, rid)
    deleted_cache = _delete_dir(cache_dir)
    deleted_outputs = _delete_dir(output_dir)
    return {
        "workflow": wf,
        "run_id": rid,
        "cache_dir": str(cache_dir),
        "output_dir": str(output_dir),
        "run_dir": str(cache_dir),
        "deleted": deleted_cache or deleted_outputs,
        "deleted_cache": deleted_cache,
        "deleted_outputs": deleted_outputs,
    }
