"""抖音创作者中心的作品管理页面和数据接口。"""

import json
from urllib.parse import urlsplit

from core.tools.publish_media.publisher_cli import run_publisher_cli

CREATOR_ORIGIN = "https://creator.douyin.com"
WORK_MANAGEMENT_PAGE = f"{CREATOR_ORIGIN}/creator-micro/content/manage"
WORK_DETAIL_PAGE = f"{CREATOR_ORIGIN}/creator-micro/work-management/work-detail/{{work_id}}"
WORK_LIST_API = f"{CREATOR_ORIGIN}/janus/douyin/creator/pc/work_list"
WORK_METRICS_API = f"{CREATOR_ORIGIN}/web/api/creator/item/mget"

WORK_LIST_PARAMS = {
    "status": 0,
    "count": 12,
    "max_cursor": 0,
    "scene": "star_atlas",
    "device_platform": "android",
    "aid": 1128,
}

WORK_METRICS_FIELDS = "metrics,review,play_info"
WORK_METRICS_HEADERS = {"Agw-Js-Conv": "str"}


def read_creator_works(account_group: str) -> dict:
    """使用发布器的账号会话读取抖音作品和指标。"""
    endpoints = {
        "listPath": urlsplit(WORK_LIST_API).path,
        "metricsPath": urlsplit(WORK_METRICS_API).path,
        "listParams": WORK_LIST_PARAMS,
        "metricsFields": WORK_METRICS_FIELDS,
        "metricsHeaders": WORK_METRICS_HEADERS,
    }
    return run_publisher_cli([
        "douyin-creator-works", "--phone", account_group, json.dumps(endpoints),
    ])
