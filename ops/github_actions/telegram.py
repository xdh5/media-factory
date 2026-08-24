"""GitHub Actions 的零依赖 Telegram 收尾通知。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _credentials() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not value]
    if missing:
        raise RuntimeError(f"缺少 Telegram GitHub Secret：{', '.join(missing)}")
    return token, chat_id


def _request(method: str, payload: dict) -> dict:
    token, chat_id = _credentials()
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps({"chat_id": chat_id, **payload}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram 返回 HTTP {exc.code}：{details}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Telegram 通知失败：{exc}") from exc
    if result.get("ok") is not True:
        raise RuntimeError(f"Telegram 拒绝通知：{result.get('description') or result}")
    message = result.get("result") or {}
    return {"sent": True, "message_id": int(message.get("message_id") or 0)}


def _failed_stages(needs: dict) -> list[str]:
    failed = []
    for job, details in needs.items():
        result = str((details or {}).get("result") or "").strip().casefold()
        if result in {"failure", "cancelled", "timed_out", "action_required"}:
            failed.append(f"{job}（{result}）")
    return failed


def notify_generic_workflow(needs_json: str, workflow_name: str, run_url: str) -> dict:
    """成功时只发送“已成功”，失败或取消时发送具体阶段。"""
    try:
        needs = json.loads(str(needs_json or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("WORKFLOW_NEEDS_JSON 不是有效 JSON") from exc
    if not isinstance(needs, dict):
        raise ValueError("WORKFLOW_NEEDS_JSON 必须是 JSON 对象")
    failed = _failed_stages(needs)
    name = str(workflow_name or "GitHub Workflow").strip()
    url = str(run_url or "").strip()
    if failed:
        text = f"⚠️ {name} 失败\n阶段：{'、'.join(failed)}"
        if url:
            text += f"\n查看：{url}"
        return _request("sendMessage", {"text": text, "disable_notification": False})
    return _request("sendMessage", {"text": "已成功", "disable_notification": True})


def notify_workflow(
    needs_json: str,
    topic: str = "",
    subject_sheet_url: str = "",
    chinese_video_url: str = "",
    korean_video_url: str = "",
) -> dict:
    """根据全部 Job 结论发送“已成功”或具体失败阶段通知。"""
    try:
        needs = json.loads(str(needs_json or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("WORKFLOW_NEEDS_JSON 不是有效 JSON") from exc
    if not isinstance(needs, dict):
        raise ValueError("WORKFLOW_NEEDS_JSON 必须是 JSON 对象")
    stage_names = {
        "prepare": "准备生产环境",
        "generate": "生成语言学习视频",
        "upload": "上传 R2",
        "publish": "四平台排期",
        "deliver": "生成下载入口",
        "upload_diagnostics": "上传失败主题图",
    }
    failed = []
    for job, details in needs.items():
        result = str((details or {}).get("result") or "").strip().casefold()
        if result in {"failure", "cancelled", "timed_out", "action_required"}:
            failed.append(f"{stage_names.get(job, job)}（{result}）")
    if failed:
        return _request(
            "sendMessage",
            {"text": "语言学习任务失败\n阶段：" + "、".join(failed), "disable_notification": False},
        )
    return _request("sendMessage", {"text": "已成功", "disable_notification": True})
