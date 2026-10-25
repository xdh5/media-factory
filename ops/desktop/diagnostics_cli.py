"""导入故障知识和执行有来源的 RAG 评估，不触发生产发布。"""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.diagnostics.evaluation import agent_metrics, evaluate_rag
from agent.diagnostics.knowledge import KnowledgeBase
from agent.diagnostics.tracing import TraceStore
from agent.settings import ROOT as PROJECT_ROOT


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["index", "rag-eval", "agent-eval", "import-errors"])
    parser.add_argument("--database", type=Path, default=ROOT / "data/desktop/agent.sqlite")
    parser.add_argument("--cases", type=Path, default=ROOT / "cache/diagnostics/cases.json")
    parser.add_argument("--documents", type=Path, default=ROOT / "cache/diagnostics/documents")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    knowledge = KnowledgeBase(args.database)
    store = TraceStore(args.database)
    if args.command == "index":
        report = {"documents": []}
        for path in args.documents.glob("*.md"):
            identity = await knowledge.ingest(path.resolve().as_posix(), path.read_text(encoding="utf-8"))
            report["documents"].append(identity)
    elif args.command == "import-errors":
        report = {"imported": 0}
        for path in (ROOT / "cache").rglob("task-*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") == "failed":
                await knowledge.ingest(path.relative_to(ROOT).as_posix(), json.dumps({"step": payload.get("step"), "error": payload.get("error")}, ensure_ascii=False), "error")
                report["imported"] += 1
    elif args.command == "rag-eval":
        data = json.loads(args.cases.read_text(encoding="utf-8"))
        # 评估使用独立的文档索引，不能混入待评估的错误查询。
        if any(item["kind"] == "error" for item in knowledge.list_documents()):
            raise ValueError("评估索引包含历史错误，请使用只收录诊断文档的独立评估数据库")
        report = await evaluate_rag(knowledge, data["cases"], args.k)
        store.save_evaluation("rag", report)
    else:
        report = agent_metrics(store)
        store.save_evaluation("agent", report)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
