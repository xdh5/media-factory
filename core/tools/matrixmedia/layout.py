"""定位本仓库内的 MatrixMedia 源码与 MCP 入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ._constants import (
    DOCUMENTS_DATA_DIR,
    MATRIXMEDIA_DIR,
    MATRIXMEDIA_MCP_ENTRY,
    MCP_TOOLS,
    PLATFORM_CN,
    WINDOWS_USERDATA_DIR,
)
from ._errors import MatrixMediaHostError, MatrixMediaMcpNotBuiltError, MatrixMediaNotFoundError


def derive_partition(phone: str, platform: str) -> str:
    """与 MatrixMedia MCP 一致：persist:{手机号}{平台中文名}。"""
    phone_seg = str(phone).strip()
    cn = PLATFORM_CN.get(platform, platform)
    return f"persist:{phone_seg}{cn}"


def require_windows_host() -> None:
    if sys.platform != "win32":
        raise MatrixMediaHostError()


def get_matrixmedia_dir() -> Path:
    if not MATRIXMEDIA_DIR.is_dir():
        raise MatrixMediaNotFoundError()
    return MATRIXMEDIA_DIR


def get_mcp_entry(*, require_built: bool = True) -> Path:
    get_matrixmedia_dir()
    if require_built and not MATRIXMEDIA_MCP_ENTRY.is_file():
        raise MatrixMediaMcpNotBuiltError()
    return MATRIXMEDIA_MCP_ENTRY


def describe_matrixmedia_layout() -> dict:
    """给 Agent 看路径和 MCP 是否已构建，不执行发布。"""
    return {
        "matrixmedia_dir": str(MATRIXMEDIA_DIR),
        "mcp_entry": str(MATRIXMEDIA_MCP_ENTRY),
        "mcp_built": MATRIXMEDIA_MCP_ENTRY.is_file(),
        "windows_userdata_dir": str(WINDOWS_USERDATA_DIR),
        "documents_data_dir": str(DOCUMENTS_DATA_DIR),
        "mcp_tools": list(MCP_TOOLS),
        "electron_run_as_node": os.environ.get("ELECTRON_RUN_AS_NODE", ""),
    }
