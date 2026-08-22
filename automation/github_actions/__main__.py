"""GitHub Actions 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json

from .finance import run as run_finance
from .language_learning import run as run_language_learning


def main() -> None:
    parser = argparse.ArgumentParser(description="媒体工厂 GitHub Actions 自动成片")
    parser.add_argument("workflow", choices=["finance", "language_learning"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--modes", default="en-zh,en-ko")
    arguments = parser.parse_args()
    if arguments.workflow == "finance":
        result = asyncio.run(run_finance(arguments.topic))
    else:
        modes = [item.strip() for item in arguments.modes.split(",") if item.strip()]
        result = asyncio.run(run_language_learning(arguments.topic, modes))
    print(json.dumps({"status": "succeeded", "r2": result["r2"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

