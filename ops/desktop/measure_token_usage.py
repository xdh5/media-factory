"""使用真实模型和历史进度重放实测等待开销，不重新采集或转写。"""

import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from agent.diagnostics.tracing import RunObserver, TraceStore
from agent.journal import CallJournal
from agent.llm import ToolCallingLLM
from agent.mcp_client import MCPTools
from agent.settings import AgentSettings, SERVERS, llm_configuration
from agent.workflow import build_graph, initial_state


async def main():
    home = Path(os.getenv("APPDATA")) / "MediaFactory"
    os.environ.update({key: value for key, value in dotenv_values(home / "config.env").items() if value is not None})
    source_task = "chat-2f0cdee73a71e66735c89b395551461845a7b75a1f3ce84505b986c52dc442d2"
    source = home / "agent.sqlite"
    with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as connection:
        records = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM agent_spans WHERE kind='tool' AND name='finance_poll_task' "
            "AND run_id IN (SELECT id FROM agent_runs WHERE task_id=?) ORDER BY started", (source_task,))]
        baseline = connection.execute("SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens) FROM agent_spans "
            "WHERE kind='llm' AND run_id IN (SELECT id FROM agent_runs WHERE task_id=?)", (source_task,)).fetchone()
    selected_path = records[-1]["arguments"]["task_path"]
    records = [record for record in records if record["arguments"]["task_path"] == selected_path]
    responses = [record["result"] for record in records]
    assert len(responses) == 28 and sum(result.get("done") is False for result in responses) == 27
    task_file = Path(str(home / "workspace/cache/collect_finance_copy") + "/" + selected_path.replace("\\", "/").split("/collect_finance_copy/")[1])
    assert task_file.is_file()
    output = ROOT / "cache/desktop-verification" / ("tokens-" + uuid.uuid4().hex)
    output.mkdir(parents=True)
    store = TraceStore(output / "agent.sqlite")
    task_id = "历史等待阶段真实模型开销实测"
    run_id = store.start(task_id)
    observer = RunObserver(store, run_id)
    class MeasuredLLM(ToolCallingLLM):
        requests = 0

        async def call(self, messages, tools):
            if self.requests >= 2:
                raise RuntimeError("实测模型请求上限为两次，停止继续消耗额度")
            self.requests += 1
            return await super().call(messages, tools)
    report = {"model": llm_configuration()["model"], "method": "真实 LLM + 历史真实工具返回重放；不重新下载或转写，不是新的完整生产耗时评测",
              "source_task": source_task, "historical_progress_count": len(responses),
              "historical_payload_sha256": hashlib.sha256(json.dumps(responses, ensure_ascii=False).encode()).hexdigest(),
              "original_task": {"llm_calls": baseline[0], "input_tokens": baseline[1], "output_tokens": baseline[2]},
              "poll_llm_counts": []}

    async with MCPTools(list(SERVERS)) as actual:
        class ReplayTools:
            instructions = actual.instructions
            index = 0

            def definitions(self):
                return actual.definitions()

            def instructions_for(self, names):
                return actual.instructions_for(names)

            def schema(self, name):
                if name != "finance_poll_task":
                    raise ValueError("本次实测只允许读取既有任务")
                return actual.schema(name)

            def read_only(self, name):
                return name == "finance_poll_task"

            async def call(self, name, arguments, timeout):
                assert name == "finance_poll_task" and arguments["task_path"] == str(task_file)
                assert self.index < len(responses), "模型重复查询了已完成任务"
                llm_count = sum(span["kind"] == "llm" for span in store.chain(run_id))
                report["poll_llm_counts"].append(llm_count)
                result = copy.deepcopy(responses[self.index])
                self.index += 1
                if self.index in {1, 13, 25, 28}:
                    print(f"进度查询 {self.index}/28，已完成模型请求 {llm_count}", flush=True)
                return result

        tools = ReplayTools()
        settings = AgentSettings(database=output / "agent.sqlite", max_steps=6, max_attempts=1, run_timeout=220)
        journal = CallJournal(settings.database)
        started = time.time()
        try:
            async with AsyncSqliteSaver.from_conn_string(str(settings.database)) as saver:
                graph = build_graph(MeasuredLLM(settings, observer, streaming=True), tools, journal, saver, settings, task_id, observer)
                task = (f"只使用 finance_poll_task 查询现有任务 {task_file}，一直等待 done=true，然后用一句话报告 saved_count。"
                        "禁止启动任务、下载、转写或调用任何其他工具；不要复述文案。")
                state = initial_state(task, tools, list(SERVERS), settings)
                state["loaded_tools"] = ["finance_poll_task"]
                result = await asyncio.wait_for(graph.ainvoke(state,
                    {"configurable": {"thread_id": task_id}, "recursion_limit": 1000}, durability="sync"), settings.run_timeout)
            spans = [span for span in store.chain(run_id) if span["kind"] == "llm"]
            assert result["status"] == "completed" and tools.index == 28
            assert all(count == 1 for count in report["poll_llm_counts"]), "等待期间发生额外模型请求"
            assert len(spans) == 2 and all(span["prompt_tokens"] is not None for span in spans)
            report["measured"] = {"llm_calls": len(spans), "input_tokens": sum(span["prompt_tokens"] for span in spans),
                "output_tokens": sum(span["completion_tokens"] for span in spans), "poll_calls": tools.index,
                "llm_calls_during_wait": 0, "elapsed_seconds": round(time.time() - started, 2)}
            # 使用真实 stdio MCP 再读取一次原任务，确认重放末态与现有业务记录一致。
            live = await actual.call("finance_poll_task", {"task_path": str(task_file)}, 60)
            assert live.get("done") is True and live.get("status") == responses[-1].get("status")
            report["live_mcp_check"] = {"done": live["done"], "status": live["status"]}
            report["status"] = "passed"
            store.finish(run_id, "completed")
        except Exception as error:
            report["status"] = "failed"
            report["error_type"] = type(error).__name__
            store.finish(run_id, "error")
            raise
        finally:
            spans = [span for span in store.chain(run_id) if span["kind"] == "llm"]
            report["incurred_usage"] = {"recorded_llm_calls": len(spans),
                "input_tokens": sum(span["prompt_tokens"] or 0 for span in spans),
                "output_tokens": sum(span["completion_tokens"] or 0 for span in spans)}
            journal.close()
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("实测报告：" + str(output / "report.json"), flush=True)
    print(json.dumps(report["measured"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
