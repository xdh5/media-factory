"""从已验收词包制作语言学习成片并交付 R2。"""
import asyncio
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from .tools.packs import language_learning_claim_pack
from .tools.packs import language_learning_get_production_config
from .tools.subject_cards import compose_fixed_cards_from_subjects
from .tools.videos import create_vocabulary_videos
from .tools.delivery import attach_publish_manifest, upload_publish_assets_to_r2
from .parameters import production_dirs, WORDS_PER_TASK
from tools.r2_files import download_file


async def run(publish_date: str, work_dir: Path, plan: dict, *, production_source: str = "local_mcp") -> dict:
    """领取词包、拼卡、配音、合成并上传，内部步骤直接传递结果。"""
    claimed = await asyncio.to_thread(language_learning_claim_pack, publish_date)
    pack, run_id = claimed["pack"], claimed["run_id"]
    topic, words = pack["topic"], pack["words"]
    modes = list(dict.fromkeys(item["learning_mode"] for item in plan["pending_outputs"]))
    config = language_learning_get_production_config(topic)
    # 补片时保留同一批次已经交付的版本，合成服务会合并发布清单。
    items = {}
    for row in plan["completed_outputs"]:
        if row["run_id"] != run_id:
            continue
        kind = str(row["content_kind"])
        mode = kind.removesuffix("-quiz")
        item = items.setdefault(kind, {"learning_mode": mode,
            "video_format": "quiz" if kind.endswith("-quiz") else "standard",
            "title": row["title"], "tags": str(row.get("hashtags") or "").split(),
            "short_title": config["publish_config"].get(mode, {}).get("short_title", ""), "videos": []})
        item["videos"].append({"content_part": int(row.get("content_part") or 1),
            "title": row["title"], "output_path": "", "video_url": row["r2_url"],
            "r2_key": unquote(urlparse(row["r2_url"]).path).lstrip("/")})
    if items:
        (Path(claimed["output_dir"]) / "publish-manifest.json").write_text(
            json.dumps({"items": list(items.values())}, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(pack["image_urls"]) != WORDS_PER_TASK:
        raise ValueError(f"词包必须包含 {WORDS_PER_TASK} 张已验收主体图")
    subject_paths = []
    for index, url in enumerate(pack["image_urls"], 1):
        path = work_dir / "pack-subjects" / run_id / f"{index:02d}.png"
        await asyncio.to_thread(download_file, unquote(urlparse(url).path).lstrip("/"), path)
        subject_paths.append(str(path))
    card_dirs = {}
    for mode in modes:
        cards = await asyncio.to_thread(compose_fixed_cards_from_subjects, subject_paths, words[mode],
            mode, words["_topic_english"], production_dirs(run_id)[0] / "cards" / mode)
        card_dirs[mode] = cards["output_dir"]
    rendered = await asyncio.to_thread(create_vocabulary_videos, card_dirs, {mode: words[mode] for mode in modes},
        run_id, topic, config["language_pause"], config["word_pause"], production_source, config["video_formats"],
        voices=config["voices"], pending_outputs=plan["pending_outputs"],
        hashtags_by_mode={mode: item["tags"] for mode, item in config["publish_config"].items()})
    manifest = attach_publish_manifest(rendered, {mode: words[mode] for mode in modes}, config["publish_config"])
    remote = await asyncio.to_thread(upload_publish_assets_to_r2, manifest["manifest_path"])
    return {"run_id": run_id, "manifest": manifest, "r2": {"manifest": {"url": remote["manifest_url"]}},
            "production_outputs": remote.get("production_outputs") or [], "topic": topic}


def start_production(publish_date: str) -> dict:
    """按计划日期领取词包，完成拼卡、配音、合成和 R2 交付。"""
    import asyncio
    from workflows.language_learning.tools.packs import language_learning_get_automation_plan
    from workflows.language_learning.parameters import production_dirs, production_run_id
    from tools.task_runner import submit_task as runner_submit_task
    plan = language_learning_get_automation_plan(publish_date)
    if not plan['should_generate']:
        return {'skipped': True, 'reason': plan['skip_reason']}
    run_id = production_run_id(publish_date)
    cache_root, _ = production_dirs(run_id)
    return {**runner_submit_task(cache_dir=cache_root, run_id=run_id, step='production', fn=lambda: asyncio.run(run(publish_date, cache_root, plan))), 'poll_tool': 'language_learning_poll_task'}
