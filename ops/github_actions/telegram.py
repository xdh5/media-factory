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


def notify_business_result(
    label: str,
    success: bool,
    run_url: str = "",
    error_message: str = "",
) -> dict:
    """成功静默推送文案，失败系统通知并附带链接与可选原因。"""
    name = str(label or "").strip()
    if success:
        return _request(
            "sendMessage",
            {"text": f"✅ {name}成功", "disable_notification": True},
        )
    text = f"❌ {name}失败"
    url = str(run_url or "").strip()
    if url:
        text += f"\n{url}"
    detail = str(error_message or "").strip()
    if detail:
        if len(detail) > 500:
            detail = detail[:500] + "…"
        text += f"\n{detail}"
    return _request("sendMessage", {"text": text, "disable_notification": False})


def _failed_stages(needs: dict) -> list[str]:
    failed = []
    for job, details in needs.items():
        result = str((details or {}).get("result") or "").strip().casefold()
        if result in {"failure", "cancelled", "timed_out", "action_required"}:
            failed.append(f"{job}（{result}）")
    return failed


def notify_manual_publish(needs_json: str, label: str, run_url: str, skipped: bool) -> dict:
    """手动发布 workflow：跳过时不通知；成功静默；失败系统推送。"""
    if skipped:
        return {"sent": False, "skipped": True}
    try:
        needs = json.loads(str(needs_json or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("WORKFLOW_NEEDS_JSON 不是有效 JSON") from exc
    if not isinstance(needs, dict):
        raise ValueError("WORKFLOW_NEEDS_JSON 必须是 JSON 对象")
    failed = _failed_stages(needs)
    if failed:
        return notify_business_result(label, False, run_url, "、".join(failed))
    return notify_business_result(label, True, run_url)
