"""删除一次生产的本地文件，保留 topic_history。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ._constants import PROJECT_DATA_ROOT, RUN_ID_PATTERN, RUNS_DIR_NAME, WORKFLOW_ID_PATTERN
from ._errors import ConfirmationRequiredError, InvalidParameterError, RunDirectoryError

__all__ = ["clear_run"]


def _run_dir(workflow: str, run_id: str) -> Path:
    wf = str(workflow or "").strip()
    rid = str(run_id or "").strip()
    if not re.fullmatch(WORKFLOW_ID_PATTERN, wf):
        raise InvalidParameterError("workflow", f"workflow 不合法：{workflow!r}")
    if not re.fullmatch(RUN_ID_PATTERN, rid):
        raise InvalidParameterError("run_id", f"run_id 必须是 run- 加至少 6 位数字，当前为 {run_id!r}")
    return (PROJECT_DATA_ROOT / wf / RUNS_DIR_NAME / rid).resolve()


def clear_run(workflow: str, run_id: str, *, confirmed: bool) -> dict:
    """删除 data/{workflow}/runs/{run_id} 整棵目录；不改话题库。"""
    if confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对删除本次生产文件的明确确认")
    target = _run_dir(workflow, run_id)
    data_root = PROJECT_DATA_ROOT.resolve()
    expected_parent = (data_root / str(workflow).strip() / RUNS_DIR_NAME).resolve()
    if target.parent != expected_parent:
        raise InvalidParameterError("run_id", f"拒绝删除：路径不在标准 runs 目录下：{target}")
    if not str(target).startswith(str(data_root)):
        raise InvalidParameterError("run_id", f"拒绝删除：路径不在 data 目录内：{target}")
    deleted = False
    if target.exists():
        if not target.is_dir():
            raise RunDirectoryError(f"拒绝删除：目标不是目录：{target}")
        shutil.rmtree(target)
        deleted = True
    leftover = target.parent
    if leftover.is_dir() and not any(leftover.iterdir()):
        leftover.rmdir()
    return {
        "workflow": str(workflow).strip(),
        "run_id": str(run_id).strip(),
        "run_dir": str(target),
        "deleted": deleted,
    }
