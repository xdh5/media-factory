"""发布账号配置、真实登录预检与会话审核。"""

from __future__ import annotations


from ..infrastructure import (
    list_account_groups,
    publisher_login_status,
    runner_submit_task,
    start_publisher_login,
)

from ..config import CACHE_ROOT
from .responses import account_groups_summary


from .common import _map_error


def publishing_list_account_groups(business_line: str | None = None, account_group: str | None = None,
                                    detailed: bool = False, platforms: list[str] | None = None) -> dict:
    """只读取账号组及平台配置，不检查登录。随后用 publishing_start_account_check 执行后台预检。"""
    try:
        payload = list_account_groups(business_line, account_group, platforms)
        return payload if detailed else {"groups": [{"name": group["name"], "business_line": group["business_line"], "platforms": [member["platform"] for member in group["members"]]} for group in payload["groups"]]}
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_start_account_check(business_line: str, account_group: str, platforms: list[str]) -> dict:
    """后台预检本次目标账号，立即返回 task_path。使用 publishing_poll_task 查看当前平台、阶段、耗时，完成后读取 all_accounts_ready 和 login_states；配置查询不代表登录通过。"""
    from core.tools.publish_media.accounts import check_account_groups
    def work(progress=None):
        return account_groups_summary(check_account_groups(business_line, account_group, platforms, progress))
    started = runner_submit_task(cache_dir=CACHE_ROOT / "account-check" / business_line / account_group,
                                 run_id="account-check-" + account_group,
                                 step="account-check:" + ",".join(sorted(platforms)), fn=work)
    return {**started, "poll_tool": "publishing_poll_task"}


def publishing_start_login(
    business_line: str,
    account_group: str,
    platform: str,
    timeout_seconds: int = 900,
    force: bool = True,
) -> dict:
    """为抖音、快手、头条或视频号启动 media-publisher 扫码登录，并返回二维码图片路径。"""
    try:
        return start_publisher_login(
            business_line,
            account_group,
            platform,
            timeout_seconds=timeout_seconds,
            force=force,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_login_status(login_id: str) -> dict:
    """轮询扫码结果；waiting_scan 时继续向用户展示 qr_path，success 后重新发布。"""
    try:
        return publisher_login_status(login_id)
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_review_session(account_ref: str, platform: str, screenshot_path: str, ready: bool, reason: str) -> dict:
    """仅在自动检测异常时，由宿主先查看 screenshot_path 的真实截图再提交。上传页正常且无登录、验证码、风控提示才可 ready=true；空白或无法确认则 ready=false 并告诉用户。不得仅凭 Cookie 或文字猜测。判断有效期五分钟，不能替代其他账号预检。"""
    from core.tools.publish_media.accounts import review_publish_session
    return review_publish_session(account_ref, platform, screenshot_path, ready, reason)
