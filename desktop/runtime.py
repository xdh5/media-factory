"""长驻 MCP 会话与可恢复聊天任务，HTTP 断线不取消业务执行。"""

import asyncio
import hashlib
import uuid

from filelock import FileLock

from agent.journal import CallJournal
from agent.settings import AgentSettings, SERVERS
from agent.interrupts import interrupt_payload, resume_value


class AgentRuntime:
    def __init__(self, database):
        self.database = database
        self.queue = asyncio.Queue()
        self.active = set()
        self.worker = None
        self.ready = asyncio.Event()

    def start(self):
        self.worker = asyncio.create_task(self.serve())

    async def stop(self):
        self.worker.cancel()
        try:
            await self.worker
        except asyncio.CancelledError:
            pass

    async def serve(self):
        # GUI 启动时准备全部工具，会话始终由同一协程建立、复用和关闭。
        try:
            from agent.mcp_client import MCPTools
            async with MCPTools(list(SERVERS)) as tools:
                self.ready.set()
                while True:
                    await self.process_task(tools, await self.queue.get())
        except Exception as exc:
            pending = []
            while not self.queue.empty():
                pending.append(self.queue.get_nowait())
            for task_id, _, _, _, _, events in pending:
                self.active.discard(task_id)
                await events.put({"kind": "error", "error": "MCP 初始化失败：" + str(exc), "task_id": task_id})
                await events.put({"kind": "done"})
            raise

    async def process_task(self, tools, item):
        task_id, model, text, response, interrupt_id, events = item
        run_id = uuid.uuid4()

        async def emit(event):
            await events.put(event)

        try:
            from agent.diagnostics.knowledge import KnowledgeBase
            knowledge = KnowledgeBase(self.database)
            settings = AgentSettings(database=self.database)
            lock = FileLock(str(self.database) + "." + hashlib.sha256(task_id.encode()).hexdigest() + ".lock", timeout=0)
            with lock:
                result = await self.execute(tools, knowledge, settings, task_id, model, text, response, interrupt_id, run_id, emit)
            await events.put({"kind": "result", "run_id": str(run_id), "task_id": task_id, **result})
        except Exception as exc:
            await events.put({"kind": "error", "error": str(exc), "task_id": task_id, "run_id": str(run_id)})
        finally:
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
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from agent.agent import create_media_agent

        async with AsyncSqliteSaver.from_conn_string(str(self.database)) as saver:
            graph = create_media_agent(None, None, saver, AgentSettings(database=self.database), task_id)
            return await graph.aget_state({"configurable": {"thread_id": task_id}})

    async def execute(self, tools, knowledge, settings, task_id, model, text, response, interrupt_id, run_id, emit):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
        from langgraph.types import Command
        from agent.agent import create_media_agent, initial_state, require_current_checkpoint
        from agent.streaming import stream_agent

        config = {"configurable": {"thread_id": task_id}, "recursion_limit": 100000,
                  "run_id": run_id, "metadata": {"thread_id": task_id}, "tags": ["桌面任务"]}
        journal = CallJournal(self.database)
        try:
            async with AsyncSqliteSaver.from_conn_string(str(self.database)) as saver:
                graph = create_media_agent(tools, journal, saver, settings, task_id, knowledge, streaming=True)
                snapshot = await graph.aget_state(config)
                require_current_checkpoint(snapshot)
                pending = [item for task in snapshot.tasks for item in task.interrupts]
                if pending:
                    current = pending[0]
                    payload = interrupt_payload(current.value)
                    if payload["kind"] == "approval" and response is None:
                        answer = text.strip().rstrip("。！!.")
                        if answer in {"同意", "批准", "确认", "确认执行", "可以", "好的", "执行吧", "同意执行", "确认发布", "可以发布"}:
                            response, interrupt_id = {"approved": True}, current.id
                        elif answer in {"拒绝", "不同意", "取消", "不执行", "不要执行", "不要发布", "取消发布"}:
                            response, interrupt_id = {"approved": False}, current.id
                    if payload["kind"] == "pause" and response is None and text.strip() in {"继续", "继续执行"}:
                        response, interrupt_id = {}, current.id
                    if payload["kind"] == "input" and response is None and text:
                        response, interrupt_id = text, current.id
                    if response is None:
                        return self.output(snapshot)
                    if current.id != interrupt_id:
                        raise ValueError("审批或确认已过期，请刷新任务状态")
                    graph_input = Command(resume={current.id: resume_value(current.value, response)})
                elif response is not None:
                    raise ValueError("任务没有等待审批，不能复用旧审批")
                elif not snapshot.values:
                    graph_input = initial_state(text, list(SERVERS))
                elif snapshot.next:
                    graph_input = None
                else:
                    if not text:
                        return self.output(snapshot)
                    graph_input = {"messages": [{"role": "user", "content": text}],
                                   "operation_scope": uuid.uuid4().hex}
                try:
                    await asyncio.wait_for(stream_agent(graph, graph_input, config, emit), settings.run_timeout)
                except ModelCallLimitExceededError:
                    return {**self.output(await graph.aget_state(config)), "status": "limit_reached"}
                except TimeoutError:
                    return {**self.output(await graph.aget_state(config)), "status": "recoverable"}
                return self.output(await graph.aget_state(config))
        finally:
            journal.close()

    @staticmethod
    def output(snapshot):
        from agent.__main__ import snapshot_output

        result = snapshot_output(snapshot)
        result["interrupts"] = [{"id": item.id, **interrupt_payload(item.value)} for task in snapshot.tasks for item in task.interrupts]
        return result
