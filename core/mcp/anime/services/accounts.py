"""从部署配置和数据库确定动漫发布账号组。"""

import os

from core.tools.media_records import list_publishing_account_groups

from .._errors import AnimeError


def production_config(account_group: str = "") -> dict:
    """显式指定优先，否则读取配置或唯一启用的 YouTube 动漫账号组。"""
    database = list_publishing_account_groups(business_line="anime")
    members = database["members"]
    candidates = [group for group in database["groups"]
                  if group.get("enabled") and any(
                      member.get("group_code") == group["code"]
                      and member.get("enabled") and member.get("platform") == "youtube"
                      for member in members)]
    selected = account_group.strip() or os.getenv("ANIME_ACCOUNT_GROUP", "").strip()
    if not selected and len(candidates) == 1:
        selected = candidates[0]["name"]
    group = next((item for item in candidates if item["name"] == selected), None)
    if group is None:
        raise AnimeError("无法唯一确定动漫 YouTube 账号组，请从候选中指定", {
            "configured_account_group": selected,
            "candidates": [item["name"] for item in candidates],
        })
    return {"account_group": group["name"], "business_line": "anime", "platform": "youtube",
            "workflow": "publish-anime-youtube.yml", "execution_mode": "github_action",
            "channels": [{"display_name": item.get("display_name"),
                          "platform_account_id": item.get("platform_account_id")}
                         for item in members if item.get("group_code") == group["code"]
                         and item.get("enabled") and item.get("platform") == "youtube"]}
