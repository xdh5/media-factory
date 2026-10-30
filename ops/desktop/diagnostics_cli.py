"""导入故障知识和 LangSmith 数据集，执行原生 RAG 实验。"""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.diagnostics.evaluation import evaluate_rag, upload_diagnostic_cases
from agent.diagnostics.knowledge import KnowledgeBase
from agent.diagnostics.tracing import agent_tracing, tracing_settings


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["index", "upload-cases", "rag-eval", "langsmith", "import-errors"])
    parser.add_argument("--database", type=Path, default=ROOT / "data/desktop/agent.sqlite")
    parser.add_argument("--cases", type=Path, default=ROOT / "cache/diagnostics/cases.json")
    parser.add_argument("--dataset", default="media-factory-diagnostics")
    parser.add_argument("--documents", type=Path, default=ROOT / "cache/diagnostics/documents")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    knowledge = KnowledgeBase(args.database)
    with agent_tracing():
        if args.command == "index":
            report = {"documents": []}
            for path in args.documents.glob("*.md"):
                report["documents"].append(await knowledge.ingest(path.resolve().as_posix(), path.read_text(encoding="utf-8")))
        elif args.command == "import-errors":
            report = {"imported": 0}
            for path in (ROOT / "cache").rglob("task-*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("status") == "failed":
                    await knowledge.ingest(path.relative_to(ROOT).as_posix(), json.dumps(
                        {"step": payload.get("step"), "error": payload.get("error")}, ensure_ascii=False), "error")
                    report["imported"] += 1
        elif args.command == "upload-cases":
            data = json.loads(args.cases.read_text(encoding="utf-8"))
            report = await asyncio.to_thread(upload_diagnostic_cases, data["cases"], args.dataset)
        elif args.command == "rag-eval":
            report = await evaluate_rag(knowledge, args.dataset, args.k)
        else:
            report = tracing_settings()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
