"""MatrixMedia MCP 输入输出约定，发布必须走 MCP，禁止本地脚本绕过。"""

from ._constants import MCP_VIDEO_PLATFORMS

LIST_ACCOUNTS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {
            "type": "string",
            "enum": list(MCP_VIDEO_PLATFORMS) + ["xhs", "juejin", "fqsp"],
        },
    },
    "additionalProperties": False,
}

PUBLISH_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": list(MCP_VIDEO_PLATFORMS)},
        "file": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "phone": {"type": "string", "minLength": 1},
        "bt2": {
            "type": "string",
            "description": "短标题。视频号必填 6～16 字；财经传 short_title / publish_bt2",
        },
        "tags": {"type": "string"},
        "address": {"type": "string"},
        "publishAt": {"type": "string"},
        "show": {"type": "boolean"},
        "draft": {"type": "boolean"},
        "creativeStatement": {"type": "string"},
        "sphProductId": {"type": "string"},
    },
    "required": ["platform", "file", "title", "phone"],
    "additionalProperties": True,
}

MCP_LAYOUT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "matrixmedia_dir": {"type": "string"},
        "mcp_entry": {"type": "string"},
        "mcp_built": {"type": "boolean"},
        "windows_userdata_dir": {"type": "string"},
        "documents_data_dir": {"type": "string"},
        "mcp_tools": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "matrixmedia_dir",
        "mcp_entry",
        "mcp_built",
        "windows_userdata_dir",
        "documents_data_dir",
        "mcp_tools",
    ],
    "additionalProperties": False,
}
