"""命令行任务入口：python -m agent。"""

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

from filelock import FileLock
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.messages import BaseMessage, convert_to_openai_messages
from langgraph.types import Command

from .journal import CallJournal
from .mcp_client import MCPTools
from .settings import AgentSettings, SERVERS
from .agent import create_media_agent, initial_state, require_current_checkpoint
from .interrupts import interrupt_payload, resume_value
from .streaming import stream_agent
from .diagnostics.knowledge import KnowledgeBase


def parser():
    command = argparse.ArgumentParser(description="Media Factory 独立 Agent")
    command.add_argument("--database", type=Path, default=AgentSettings.database)
    subcommands = command.add_subparsers(dest="command", required=True)
    for name in ("run", "resume", "status", "pause"):
        action = subcommands.add_parser(name)
        action.add_argument("task_id", help="持久化任务 ID")
        if name in {"run", "resume"}:
            action.add_argument("--tool-timeout", type=float, default=180)
            action.add_argument("--run-timeout", type=float, default=1800)
            action.add_argument("--llm-timeout", type=float, default=180)
            action.add_argument("--max-attempts", type=int, default=3)
            action.add_argument("--max-llm-tokens", type=int, default=100000)
            action.add_argument("--max-steps", type=int, default=60, help="每次执行的模型调用次数上限")
        if name == "run":
            action.add_argument("task", help="自然语言任务")
            action.add_argument("--servers", nargs="+", choices=list(SERVERS), default=["finance"])

        if name == "resume":
            action.add_argument("--response", help="审批、人工回答或核对回执的 JSON")
    return command


def snapshot_output(snapshot):
    interrupts = [interrupt_payload(item.value) for task in snapshot.tasks for item in task.interrupts]
    last_message = (snapshot.values.get("messages") or [None])[-1]
    if isinstance(last_message, BaseMessage):
        last_message = convert_to_openai_messages(last_message)
    return {"status": "paused" if interrupts else (
        "recoverable" if snapshot.next else "completed" if snapshot.values else "unknown"),
        "steps": snapshot.values.get("thread_model_call_count", snapshot.values.get("steps", 0)),
        "next": list(snapshot.next), "interrupts": interrupts, "last_message": last_message}


async def execute_command(arguments):
    settings = AgentSettings(database=arguments.database.resolve(), **{
        name: getattr(arguments, name) for name in (
            "tool_timeout", "run_timeout", "llm_timeout", "max_steps", "max_attempts", "max_llm_tokens")
        if hasattr(arguments, name)})
    settings.database.parent.mkdir(parents=True, exist_ok=True)
    journal = CallJournal(settings.database)
    try:
        if arguments.command == "pause":
            journal.pause(arguments.task_id)
            return {"status": "pause_requested", "message": "当前操作完成后在下一边界暂停"}
        async with AsyncSqliteSaver.from_conn_string(str(settings.database)) as saver:
            config = {"configurable": {"thread_id": arguments.task_id}, "recursion_limit": 100000,
                      "run_id": uuid.uuid4(), "metadata": {"thread_id": arguments.task_id}, "tags": ["命令行任务"]}
            graph = create_media_agent(None, journal, saver, settings, arguments.task_id)
            snapshot = await graph.aget_state(config)
            if arguments.command == "status":
                if not snapshot.values:
                    raise ValueError("任务不存在")
                return snapshot_output(snapshot)
            if arguments.command == "run":
                if snapshot.values:
                    raise ValueError("任务 ID 已存在，请使用 resume 或新的 ID")
                servers = arguments.servers
            else:
                require_current_checkpoint(snapshot)
                if not snapshot.values:
                    raise ValueError("任务不存在")
                if not snapshot.next:
                    return snapshot_output(snapshot)
                servers = snapshot.values["servers"]
            async with MCPTools(servers, session_timeout=settings.llm_timeout) as tools:
                knowledge = KnowledgeBase(settings.database)
                graph = create_media_agent(tools, journal, saver, settings, arguments.task_id, knowledge)
                if arguments.command == "run":
                    graph_input = initial_state(arguments.task, servers)
                else:
                    pending = [item for task in snapshot.tasks for item in task.interrupts]
                    if pending:
                        if arguments.response is None:
                            raise ValueError("任务等待人工输入，请使用 --response 提供 JSON")
                        response = resume_value(pending[0].value, json.loads(arguments.response))
                        graph_input = Command(resume={pending[0].id: response})
                    else:
                        if arguments.response is not None:
                            raise ValueError("当前没有等待处理的人工中断")
                        graph_input = None
                try:
                    await asyncio.wait_for(stream_agent(graph, graph_input, config), settings.run_timeout)
                except ModelCallLimitExceededError:
                    return {**snapshot_output(await graph.aget_state(config)), "status": "limit_reached"}
                except TimeoutError:
                    return {**snapshot_output(await graph.aget_state(config)),
                            "message": "本次执行超时，已保留检查点；使用 resume 继续"}
                result = snapshot_output(await graph.aget_state(config))
                result["run_id"] = str(config["run_id"])
                return result
    finally:
        journal.close()


def main():
    arguments = parser().parse_args()
    arguments.database = arguments.database.resolve()
    arguments.database.parent.mkdir(parents=True, exist_ok=True)
    task_hash = hashlib.sha256(arguments.task_id.encode()).hexdigest()
    lock = FileLock(str(arguments.database) + "." + task_hash + ".lock", timeout=0)
    try:
        # 状态查询和暂停请求允许与执行进程并行。
        if arguments.command in {"status", "pause"}:
            result = asyncio.run(execute_command(arguments))
        else:
            with lock:
                result = asyncio.run(execute_command(arguments))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        print("执行已中断，可使用相同任务 ID 恢复。", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"执行失败：{type(exc).__name__}：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
