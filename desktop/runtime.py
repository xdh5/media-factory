"""长驻 MCP 会话与可恢复聊天任务，HTTP 断线不取消业务执行。"""

import asyncio
import hashlib
import json
import time
import uuid

from filelock import FileLock
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START
from langgraph.types import Command

from agent.__main__ import snapshot_output
from agent.diagnostics.knowledge import KnowledgeBase
from agent.diagnostics.tracing import RunObserver, TraceStore
from agent.journal import CallJournal
from agent.llm import ToolCallingLLM
from agent.mcp_client import MCPTools
from agent.settings import AgentSettings, SERVERS
from agent.workflow import build_graph, initial_state
from agent.approval_policy import requires_approval


class AgentRuntime:
    def __init__(self, database):
        self.database = database
        self.store = TraceStore(database)
        self.queue = asyncio.Queue()
        self.active = set()
        self.worker = None

    def start(self):
        self.worker = asyncio.create_task(self.serve())

    async def stop(self):
        self.worker.cancel()
        try:
            await self.worker
        except asyncio.CancelledError:
            pass

    async def serve(self):
        # MCP 上下文始终由同一协程进入和退出；人工审批不会关闭后台任务所属的服务。
        async with MCPTools(list(SERVERS)) as tools:
            while True:
                task_id, model, text, response, interrupt_id, events = await self.queue.get()
                run_id = self.store.start(task_id)
                async def emit(event):
                    await events.put(event)
                knowledge = KnowledgeBase(self.database)
                observer = RunObserver(self.store, run_id, emit, knowledge)
                knowledge.observer = observer
                try:
                    settings = AgentSettings(database=self.database)
                    lock = FileLock(str(self.database) + "." + hashlib.sha256(task_id.encode()).hexdigest() + ".lock", timeout=0)
                    with lock:
                        result = await self.execute(tools, observer, settings, task_id, model, text, response, interrupt_id)
                    self.store.finish(run_id, result["status"])
                    await events.put({"kind": "result", "run_id": run_id, "task_id": task_id, **result})
                except Exception as exc:
                    await observer.event("run", "任务异常", {"error": str(exc)}, status="error")
                    self.store.finish(run_id, "error")
                    await events.put({"kind": "error", "error": str(exc), "task_id": task_id, "run_id": run_id})
                finally:
                    self.store.finish_interrupted(run_id)
                    self.active.discard(task_id)
                    await events.put({"kind": "done"})

    async def submit(self, task_id, model, text="", response=None, interrupt_id=None):
        if self.worker.done():
            exception = self.worker.exception()
            raise RuntimeError(f"MCP 服务不可用：{exception}")
        if task_id in self.active:
            raise ValueError("此任务正在执行，请先查看状态")
        self.active.add(task_id)
        events = asyncio.Queue()
        await self.queue.put((task_id, model, text, response, interrupt_id, events))
        return events

    async def snapshot(self, task_id):
        async with AsyncSqliteSaver.from_conn_string(str(self.database)) as saver:
            graph = build_graph(None, None, None, saver, AgentSettings(database=self.database), task_id)
            return await graph.aget_state({"configurable": {"thread_id": task_id}})

    async def execute(self, tools, observer, settings, task_id, model, text, response, interrupt_id):
        config = {"configurable": {"thread_id": task_id}, "recursion_limit": 100000}
        journal = CallJournal(self.database)
        try:
            async with AsyncSqliteSaver.from_conn_string(str(self.database)) as saver:
                graph = build_graph(ToolCallingLLM(settings, observer, streaming=True), tools, journal, saver, settings, task_id, observer)
                snapshot = await graph.aget_state(config)
                pending = [item for task in snapshot.tasks for item in task.interrupts]
                if pending:
                    current = pending[0]
                    if current.value["kind"] == "approval" and not requires_approval(
                        current.value["tool"], current.value.get("arguments", {}), False):
                        response, interrupt_id = {"approved": True}, current.id
                    if current.value["kind"] == "uncertain":
                        response, interrupt_id = {}, current.id
                    if current.value["kind"] == "approval" and response is None:
                        answer = text.strip().rstrip("。！!.")
                        if answer in {"同意", "批准", "确认", "确认执行", "可以", "好的", "执行吧", "同意执行", "确认发布", "可以发布"}:
                            response, interrupt_id = {"approved": True}, current.id
                        elif answer in {"拒绝", "不同意", "取消", "不执行", "不要执行", "不要发布", "取消发布"}:
                            response, interrupt_id = {"approved": False}, current.id
                    if current.value["kind"] == "pause" and response is None and text.strip() in {"继续", "继续执行"}:
                        response, interrupt_id = {}, current.id
                    if current.value["kind"] == "input" and response is None and text:
                        response, interrupt_id = text, current.id
                    if response is None:
                        return self.output(snapshot)
                    if current.id != interrupt_id:
                        raise ValueError("审批或确认已过期，请刷新任务状态")
                    kind = current.value["kind"]
                    if kind == "approval" and (not isinstance(response, dict) or type(response.get("approved")) is not bool):
                        raise ValueError("审批必须包含明确的 approved 布尔值")
                    await observer.event("human", kind, {"interrupt_id": current.id, "response": response})
                    graph_input = Command(resume={current.id: response})
                elif response is not None:
                    raise ValueError("任务没有等待审批，不能复用旧审批")
                elif not snapshot.values:
                    state = initial_state(text, tools, list(SERVERS), settings)
                    state["operation_scope"] = uuid.uuid4().hex
                    await graph.aupdate_state(config, state, as_node=START)
                    graph_input = None
                elif snapshot.values["status"] == "limit_reached":
                    update = {"status": "running", "max_steps": snapshot.values["steps"] + settings.max_steps}
                    if text and not snapshot.values.get("pending"):
                        update["messages"] = snapshot.values["messages"] + [{"role": "user", "content": text}]
                    # 延续同一操作范围和未完成调用，已完成的副作用继续复用回执。
                    await graph.aupdate_state(config, update, as_node=START)
                    graph_input = None
                elif snapshot.next:
                    graph_input = None
                else:
                    if not text:
                        return self.output(snapshot)
                    await graph.aupdate_state(config, {"messages": snapshot.values["messages"] + [{"role": "user", "content": text}],
                        "pending": [], "status": "running", "operation_scope": uuid.uuid4().hex,
                        "loaded_tools": [],
                        "max_steps": snapshot.values["steps"] + settings.max_steps}, as_node=START)
                    graph_input = None
                try:
                    await asyncio.wait_for(graph.ainvoke(graph_input, config, durability="sync"), settings.run_timeout)
                except TimeoutError:
                    await observer.event("run", "执行预算耗尽", {"timeout_seconds": settings.run_timeout}, status="error")
                return self.output(await graph.aget_state(config))
        finally:
            journal.close()

    @staticmethod
    def output(snapshot):
        result = snapshot_output(snapshot)
        result["interrupts"] = [{"id": item.id, **item.value} for task in snapshot.tasks for item in task.interrupts]
        return result
