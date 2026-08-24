"""GitHub Actions 视频创建命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="媒体工厂 GitHub Actions 视频创建")
    parser.add_argument(
        "workflow",
        choices=[
            "finance_preflight",
            "finance_restore_library",
            "finance_upload_libraries",
            "finance",
            "language_learning_preflight",
            "language_learning_words",
            "language_learning_cards",
            "language_learning_recompose_cards",
            "language_learning_videos",
            "language_learning_r2",
            "language_learning_diagnostics_r2",
            "language_learning_publish",
            "language_learning_notify",
            "workflow_notify",
        ],
    )
    parser.add_argument("--topic", default="")
    parser.add_argument("--modes", default="en-zh,en-ko")
    parser.add_argument("--state-path", default="cache/github_actions/language-learning-state.json")
    parser.add_argument("--handoff-dir", default="cache/github_actions/language-learning-handoff")
    parser.add_argument("--diagnostics-dir", default="cache/github_actions/language-learning-diagnostics")
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--manifest-url", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--topic-value", default="")
    parser.add_argument("--subject-sheet-url", default="")
    parser.add_argument("--chinese-video-url", default="")
    parser.add_argument("--korean-video-url", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--publish-date", default="")
    parser.add_argument("--default-days-ahead", type=int, choices=(0, 1), default=0)
    parser.add_argument("--library-line", default="finance_generated")
    parser.add_argument("--workflow-name", default="")
    parser.add_argument("--run-url", default="")
    arguments = parser.parse_args()
    if arguments.workflow in {"finance_preflight", "language_learning_preflight"}:
        from ._shared import daily_production_preflight

        business_line = "finance" if arguments.workflow == "finance_preflight" else "language_learning"
        payload = daily_production_preflight(
            business_line,
            arguments.publish_date,
            arguments.default_days_ahead,
        )
        output_path = os.getenv("GITHUB_OUTPUT", "").strip()
        if output_path:
            with Path(output_path).open("a", encoding="utf-8") as stream:
                stream.write(f"publish_date={payload['publish_date']}\n")
                stream.write(f"should_generate={str(payload['should_generate']).lower()}\n")
                stream.write(f"should_resume_publish={str(payload['should_resume_publish']).lower()}\n")
                stream.write(f"existing_run_id={payload['existing_run_id']}\n")
                stream.write(f"pending_targets={','.join(payload['pending_targets'])}\n")
                stream.write(f"skip_reason={payload['skip_reason']}\n")
    elif arguments.workflow == "finance_restore_library":
        from ._shared import restore_finance_image_library

        library = restore_finance_image_library(arguments.library_line)
        payload = {"status": "succeeded", "library_line": arguments.library_line, "library_path": str(library)}
    elif arguments.workflow == "finance_upload_libraries":
        from core.tools.generate_image.pack_libraries import upload_finance_libraries

        payload = {"status": "succeeded", **upload_finance_libraries()}
    elif arguments.workflow == "finance":
        from .finance import run as run_finance

        result = asyncio.run(run_finance(arguments.topic, arguments.publish_date))
        payload = {"status": "succeeded", "r2": result["r2"]}
    elif arguments.workflow == "language_learning_words":
        from .language_learning import generate_words

        modes = [item.strip() for item in arguments.modes.split(",") if item.strip()]
        result = asyncio.run(
            generate_words(arguments.topic, modes, arguments.state_path, arguments.publish_date)
        )
        payload = {"status": "succeeded", "run_id": result["run_id"], "topic": result["topic"]}
    elif arguments.workflow == "language_learning_cards":
        from .language_learning import generate_cards

        result = asyncio.run(generate_cards(arguments.state_path, arguments.diagnostics_dir))
        payload = {"status": "succeeded", "card_dirs": result["card_dirs"]}
    elif arguments.workflow == "language_learning_recompose_cards":
        from .language_learning import recompose_cards_from_r2

        result = asyncio.run(
            recompose_cards_from_r2(
                arguments.source_run_id,
                arguments.state_path,
                arguments.publish_date,
            )
        )
        payload = {"status": "succeeded", "run_id": result["run_id"], "card_dirs": result["card_dirs"]}
    elif arguments.workflow == "language_learning_videos":
        from .language_learning import generate_videos

        result = asyncio.run(generate_videos(arguments.state_path, arguments.handoff_dir))
        payload = {"status": "succeeded", "run_id": result["run_id"], "video_files": result["video_files"]}
    elif arguments.workflow == "language_learning_r2":
        from .language_learning import upload_handoff

        result = upload_handoff(arguments.handoff_dir)
        payload = {"status": "succeeded", "r2": result["r2"]}
        output_path = os.getenv("GITHUB_OUTPUT", "").strip()
        if output_path:
            with Path(output_path).open("a", encoding="utf-8") as stream:
                stream.write(f"manifest_url={result['r2']['manifest']['url']}\n")
                stream.write(f"run_id={result['manifest']['run_id']}\n")
                stream.write(f"topic={result['topic']}\n")
                stream.write(f"subject_sheet_url={result['subject_sheet_url']}\n")
                stream.write(f"chinese_video_url={result['download_urls'].get('en-zh', '')}\n")
                stream.write(f"korean_video_url={result['download_urls'].get('en-ko', '')}\n")
    elif arguments.workflow == "language_learning_diagnostics_r2":
        from .language_learning import upload_failed_subject_sheets

        payload = upload_failed_subject_sheets(arguments.diagnostics_dir)
    elif arguments.workflow == "language_learning_publish":
        from .language_learning import schedule_publication

        targets = [item.strip() for item in arguments.targets.split(",") if item.strip()]
        payload = asyncio.run(
            schedule_publication(arguments.manifest_url, arguments.run_id, targets=targets or None)
        )
    elif arguments.workflow == "language_learning_notify":
        from .telegram import notify_workflow

        payload = notify_workflow(
            os.getenv("WORKFLOW_NEEDS_JSON", "{}"),
            arguments.topic_value,
            arguments.subject_sheet_url,
            arguments.chinese_video_url,
            arguments.korean_video_url,
        )
    else:
        from .telegram import notify_generic_workflow

        payload = notify_generic_workflow(
            os.getenv("WORKFLOW_NEEDS_JSON", "{}"),
            arguments.workflow_name,
            arguments.run_url,
        )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
