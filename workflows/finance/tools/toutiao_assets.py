"""准备头条文章的三等分随机插图与独立发布素材。"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path


def prepare_toutiao_assets(manifest: dict) -> dict:
    output = Path(manifest["output_dir"])
    paragraphs = [line.strip() for line in manifest["article"].splitlines() if line.strip()]
    shots = manifest["shots"][:-1]
    plan_path = output / "toutiao-article.json"
    if plan_path.is_file():
        selected = json.loads(plan_path.read_text(encoding="utf-8"))["image_indices"]
    else:
        selected = [random.randrange(len(shots) * part // 3, len(shots) * (part + 1) // 3) for part in range(3)]
    illustrations = {}
    fields = {}
    for number, index in enumerate(selected, 1):
        destination = output / f"article-illustration-{number}.png"
        source = Path(str(shots[index].get("image_path") or ""))
        if source.is_file():
            shutil.copy2(source, destination)
        elif not destination.is_file():
            subprocess.run(["ffmpeg", "-y", "-ss", str(shots[index]["audio_start"]), "-i", manifest["video_path"],
                            "-frames:v", "1", str(destination)], check=True, capture_output=True)
        illustrations[index] = destination.name
        fields[f"article_image_{number}_path"] = str(destination)
    payload = {"title": manifest["title"], "image_indices": selected,
               "paragraphs": [{"text": text, "image": illustrations.get(index)} for index, text in enumerate(paragraphs)],
               "cover": "cover.png"}
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    article = output / "article.txt"
    article.write_text(manifest["article"], encoding="utf-8")
    summary = output / "micro-summary.txt"
    summary.write_text(str(manifest.get("micro_summary") or ""), encoding="utf-8")
    return {**fields, "toutiao_article_path": str(plan_path), "article_path": str(article), "micro_summary_path": str(summary)}
