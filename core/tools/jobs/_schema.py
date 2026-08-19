"""enqueue_job / get_job / wait_task 的真实入参和返回合同。"""

from __future__ import annotations

ENQUEUE_JOB_INPUT_SCHEMA = {
    "type": "object",
    "description": "enqueue_job(...) 的关键字参数合同",
    "properties": {
        "workflow": {"type": "string", "minLength": 1, "description": "工作流 id，如 finance"},
        "job_type": {"type": "string", "minLength": 1, "description": "该工作流内的任务类型"},
        "payload": {"type": "object", "description": "传给 handler 的输入对象"},
        "handler": {
            "type": "string",
            "description": "独立进程中调用的模块函数，格式 module.path:function",
        },
        "database_path": {"type": "string", "description": "可选；默认 data/media_factory.sqlite3"},
    },
    "required": ["workflow", "job_type", "payload", "handler"],
    "additionalProperties": False,
}

GET_JOB_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "workflow": {"type": "string", "description": "可选；传入则必须与任务所属工作流一致"},
        "database_path": {"type": "string"},
    },
    "required": ["job_id"],
    "additionalProperties": False,
}

WAIT_TASK_INPUT_SCHEMA = {
    "type": "object",
    "description": "wait_task(...) 阻塞等到 completed/failed；SQLite 为真相，Redis Stream 只负责唤醒",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "workflow": {"type": "string", "description": "可选；传入则必须与任务所属工作流一致"},
        "database_path": {"type": "string"},
        "timeout": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": 180,
            "description": "单次最多阻塞秒数，默认 180；超时仍 queued/running 则再调一次 wait_task",
        },
    },
    "required": ["job_id"],
    "additionalProperties": False,
}

JOB_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "workflow": {"type": "string"},
        "job_type": {"type": "string"},
        "status": {"type": "string", "enum": ["queued", "running", "completed", "failed"]},
        "progress_message": {"type": "string"},
        "result": {"type": ["object", "null"]},
        "error": {"type": ["object", "null"]},
        "created_at": {"type": "string"},
        "started_at": {"type": ["string", "null"]},
        "finished_at": {"type": ["string", "null"]},
        "updated_at": {"type": "string"},
    },
    "required": [
        "job_id", "workflow", "job_type", "status", "progress_message",
        "result", "error", "created_at", "started_at", "finished_at", "updated_at",
    ],
    "additionalProperties": False,
}
