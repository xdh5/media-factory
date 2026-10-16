"""按成功任务登记的保留期限清理视频，保留执行包、发布回执和结果。"""

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core
from core.tools.media_files.storage import _client, _settings


def retention_policy(execution_id, manifest, now=None):
    """保留检查点三天、成片七天；只有成功任务才调用。"""
    now = now or datetime.now(timezone.utc)
    names = [Path(part["video_path"]).name for part in manifest["parts"]]
    if any(not re.fullmatch(r"part-\d+\.mp4", name) for name in names):
        raise ValueError("成片清理计划包含无效文件名")
    return {"version": 1, "execution_id": execution_id, "succeeded_at": now.isoformat(),
            "checkpoint_expires_at": (now + timedelta(days=3)).isoformat(),
            "final_expires_at": (now + timedelta(days=7)).isoformat(),
            "final_files": names + ["manifest.json"],
            "checkpoint_cleaned": False, "final_cleaned": False}


def cleanup_policy(client, bucket, key, policy, now, dry_run=False):
    """仅删除登记的执行目录中已到期的视频，清理成功后标记进度。"""
    execution_id = policy.get("execution_id", "")
    prefix = f"runs/anime/executions/{execution_id}"
    if (not re.fullmatch(r"[a-f0-9]{32}", execution_id) or key != f"{prefix}/retention.json"
            or policy.get("version") != 1):
        raise ValueError("清理计划身份或路径不一致")
    for kind in ("checkpoint", "final"):
        if policy.get(f"{kind}_cleaned") or datetime.fromisoformat(policy[f"{kind}_expires_at"]) > now:
            continue
        if kind == "checkpoint":
            keys = [f"{prefix}/block-checkpoint.json"]
            for page in client.get_paginator("list_objects_v2").paginate(
                    Bucket=bucket, Prefix=f"{prefix}/checkpoint-blocks/"):
                keys.extend(item["Key"] for item in page.get("Contents", []))
        else:
            names = policy["final_files"]
            if any(name != "manifest.json" and not re.fullmatch(r"part-\d+\.mp4", name) for name in names):
                raise ValueError("清理计划包含非成片文件")
            keys = [f"{prefix}/{name}" for name in names]
        print(json.dumps({"execution_id": execution_id, "清理类别": kind,
                          "对象数量": len(keys), "只读预览": dry_run}, ensure_ascii=False), flush=True)
        if dry_run:
            continue
        for offset in range(0, len(keys), 1000):
            response = client.delete_objects(Bucket=bucket, Delete={
                "Objects": [{"Key": name} for name in keys[offset:offset + 1000]], "Quiet": True})
            if response.get("Errors"):
                raise RuntimeError("部分到期视频删除失败，下次继续清理")
        policy[f"{kind}_cleaned"] = True
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(policy, ensure_ascii=False).encode(),
                          ContentType="application/json")


def cleanup_expired_files(dry_run=False):
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    bucket = settings["R2_BUCKET"]
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="runs/anime/executions/"):
        keys.extend(item["Key"] for item in page.get("Contents", []) if item["Key"].endswith("/retention.json"))
    now = datetime.now(timezone.utc)
    for key in keys:
        policy = json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
        cleanup_policy(client, bucket, key, policy, now, dry_run)
    print(f"已检查 {len(keys)} 个成功任务的保留计划", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理成功动漫任务的到期视频")
    parser.add_argument("--dry-run", action="store_true", help="只读列出到期对象，不删除")
    cleanup_expired_files(parser.parse_args().dry_run)
