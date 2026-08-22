"""GitHub Actions 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="媒体工厂 GitHub Actions 自动生产与阿里云发布")
    parser.add_argument(
        "workflow",
        choices=[
            "finance",
            "language_learning",
            "language_learning_words",
            "language_learning_cards",
            "language_learning_videos",
            "language_learning_r2",
            "language_learning_diagnostics_r2",
            "publish",
        ],
    )
    parser.add_argument("--topic", default="")
    parser.add_argument("--modes", default="en-zh,en-ko")
    parser.add_argument("--manifest-url", default="")
    parser.add_argument("--state-path", default="cache/github_actions/language-learning-state.json")
    parser.add_argument("--handoff-dir", default="cache/github_actions/language-learning-handoff")
    parser.add_argument("--diagnostics-dir", default="cache/github_actions/language-learning-diagnostics")
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
    elif arguments.workflow == "language_learning_words":
        from .language_learning import generate_words

        modes = [item.strip() for item in arguments.modes.split(",") if item.strip()]
        result = asyncio.run(generate_words(arguments.topic, modes, arguments.state_path))
        payload = {"status": "succeeded", "run_id": result["run_id"], "topic": result["topic"]}
    elif arguments.workflow == "language_learning_cards":
        from .language_learning import generate_cards

        result = asyncio.run(generate_cards(arguments.state_path, arguments.diagnostics_dir))
        payload = {"status": "succeeded", "card_dirs": result["card_dirs"]}
    elif arguments.workflow == "language_learning_videos":
        from .language_learning import generate_videos

        result = asyncio.run(generate_videos(arguments.state_path, arguments.handoff_dir))
        payload = {"status": "succeeded", "run_id": result["run_id"], "video_files": result["video_files"]}
    elif arguments.workflow == "language_learning_r2":
        from .language_learning import upload_handoff

        result = upload_handoff(arguments.handoff_dir)
        payload = {"status": "succeeded", "r2": result["r2"]}
    elif arguments.workflow == "language_learning_diagnostics_r2":
        from .language_learning import upload_failed_subject_sheets

        payload = upload_failed_subject_sheets(arguments.diagnostics_dir)
    else:
        from .publish import run as run_publish

        result = run_publish(arguments.manifest_url)
        payload = {"status": "succeeded", "result": result}
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
