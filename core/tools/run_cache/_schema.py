"""clear_run 的真实入参和返回合同。"""

from __future__ import annotations

CLEAR_RUN_INPUT_SCHEMA = {
    "type": "object",
    "description": "clear_run(...) 的关键字参数合同",
    "properties": {
        "workflow": {"type": "string", "minLength": 1, "description": "工作流 id，如 finance"},
        "run_id": {"type": "string", "minLength": 1, "description": "本次生产 id，如 run-000001"},
        "confirmed": {"type": "boolean", "const": True, "description": "必须为 true，表示用户已确认删除本次生产文件"},
    },
    "required": ["workflow", "run_id", "confirmed"],
    "additionalProperties": False,
}

CLEAR_RUN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow": {"type": "string"},
        "run_id": {"type": "string"},
        "run_dir": {"type": "string"},
        "deleted": {"type": "boolean"},
    },
    "required": ["workflow", "run_id", "run_dir", "deleted"],
    "additionalProperties": False,
}
