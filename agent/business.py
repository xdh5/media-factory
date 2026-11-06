"""业务路由和各专用 Agent 的资源范围。"""

from .diagnostics.tracing import agent_tracing


BUSINESSES = {
    "anime": ("动漫", ("anime",), ("produce-anime-video",)),
    "finance": ("财经", ("finance",), ("collect-finance-copy", "produce-finance-video")),
    "language_learning": ("语言学习", ("language_learning",), (
        "produce-language-learning-pack", "produce-language-learning-video")),
    "publishing": ("发布", ("publishing", "anime"), (
        "publish-finance", "publish-korean", "publish-anime-youtube")),
}

ANIME_PRODUCTION_TOOLS = {
    "anime_get_production_config", "anime_discover_series", "anime_inspect_sources",
    "anime_start_compile", "anime_get_task",
}
ANIME_PUBLISHING_TOOLS = (ANIME_PRODUCTION_TOOLS - {"anime_start_compile"}) | {
    "anime_prepare_publication", "anime_save_publication_assets", "anime_start_publication",
}


def business_tools(tools, business):
    _, servers, _ = BUSINESSES[business]
    anime_tools = ANIME_PUBLISHING_TOOLS if business == "publishing" else ANIME_PRODUCTION_TOOLS
    return tools.scoped(servers, anime_tools)


ROUTING_QUESTION = "这项任务属于动漫制作、财经、语言学习还是发布？如果涉及多项独立任务，请先选一项。"
ROUTING_PROMPT = """只返回一个业务标识，不执行任务：
publishing：账号预检、登录、上传、预约或发布，包含找剧后发 YouTube。
anime：找剧、查集数或制作动漫。
finance：财经或情感稿件采集、定稿和制作。
language_learning：语言学习词包、图包或视频制作。
按本轮动作分类，明确发布优先；补充参数、登录恢复、进度和记忆偏好沿用上轮业务。多项独立业务、范围外或无法判断时返回 unknown。只按请求内容分类。"""
async def route_business(settings, text, previous_business=None, config=None):
    from .llm import create_chat_model

    previous = BUSINESSES[previous_business][0] if previous_business else "无"
    with agent_tracing():
        answer = await create_chat_model(settings, tools_enabled=False).ainvoke(
            [("system", ROUTING_PROMPT), ("user", f"上轮业务：{previous}\n本轮请求：{text}")],
            config=config,
        )
    business = answer.text.strip()
    return business if business in BUSINESSES else None
