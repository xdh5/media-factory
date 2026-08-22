"""GitHub Actions 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="媒体工厂 GitHub Actions 自动生产与阿里云发布")
    parser.add_argument("workflow", choices=["finance", "language_learning", "publish"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--modes", default="en-zh,en-ko")
    parser.add_argument("--manifest-url", default="")
    arguments = parser.parse_args()
    if arguments.workflow == "finance":
        from .finance import run as run_finance

        result = asyncio.run(run_finance(arguments.topic))
        payload = {"status": "succeeded", "r2": result["r2"]}
    elif arguments.workflow == "language_learning":
        from .language_learning import run as run_language_learning

        modes = [item.strip() for item in arguments.modes.split(",") if item.strip()]
        result = asyncio.run(run_language_learning(arguments.topic, modes))
        payload = {"status": "succeeded", "r2": result["r2"]}
    else:
        from .publish import run as run_publish

        result = run_publish(arguments.manifest_url)
        payload = {"status": "succeeded", "result": result}
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
