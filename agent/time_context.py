"""动态本地时间上下文与宿主日期计算。"""

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool


class TimeContextMiddleware(AgentMiddleware):
    """每次模型请求读取运行电脑时间，不将启动时间永久缓存。"""

    def prepare(self, request):
        now = datetime.now().astimezone()
        context = (
            f"当前电脑本地时间：{now.isoformat()}；时区名称：{now.tzname()}；"
            f"星期：{now.isoweekday()}（周一为1）；本周从周一开始。\n"
            "今天、明天、下周等相对日期以本轮当前时间为基准。你负责理解时间意图，"
            "必须使用 agent_calculate_datetime 让 Python 精确计算日期、时间和时区，reference_time 传上述时间。"
            "用户明确指定其他时区时遵从用户，使用 IANA 时区名称；未指定时使用电脑本地时区。"
            "最终时间输出带偏移的 ISO 8601；只有日期时明确说明尚无具体时刻，不得擅自补零点。"
            "表达存在歧义或缺少必要时间信息时调用 agent_request_input 询问，不得猜测。"
        )
        content = list(request.system_message.content_blocks) if request.system_message else []
        return request.override(system_message=SystemMessage(content=[*content, {"type": "text", "text": context}]))

    def wrap_model_call(self, request, handler):
        return handler(self.prepare(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self.prepare(request))


@tool
def agent_calculate_datetime(reference_time: str, days: int = 0, weeks: int = 0,
                             weekday: int | None = None, date: str | None = None,
                             clock: str | None = None, timezone_name: str | None = None) -> dict:
    """用 Python 计算时间。reference_time 为本轮注入的带时区 ISO 时间；days 为相对天数；weeks 为相对周数；weekday 为周一1到周日7（指定后按目标周定位）；date 为明确的 YYYY-MM-DD，不能与相对日期参数混用；clock 为用户或已确认业务规则指定的 HH:MM[:SS]，缺省只返回日期；timezone_name 为用户指定的 IANA 时区，缺省使用电脑本地时区。"""
    reference = datetime.fromisoformat(reference_time)
    if reference.tzinfo is None:
        raise ValueError("reference_time 必须带时区")
    zone = ZoneInfo(timezone_name) if timezone_name else None
    local = reference.astimezone(zone)
    if date is not None:
        if days or weeks or weekday is not None:
            raise ValueError("明确日期不能与相对日期参数混用")
        target = datetime.strptime(date, "%Y-%m-%d").date()
    else:
        target = local.date() + timedelta(days=days, weeks=weeks)
        if weekday is not None:
            if not 1 <= weekday <= 7:
                raise ValueError("weekday 必须在 1 到 7 之间")
            target += timedelta(days=weekday - target.isoweekday())
    if clock is None:
        return {"date": target.isoformat(), "timezone": timezone_name or "电脑本地时区", "requires_clock": True}
    parsed_clock = time.fromisoformat(clock)
    if parsed_clock.tzinfo is not None:
        raise ValueError("clock 不携带时区，请通过 timezone_name 指定")
    naive = datetime.combine(target, parsed_clock)
    result = naive.replace(tzinfo=zone) if zone else naive.astimezone()
    if zone and (result.utcoffset() != result.replace(fold=1).utcoffset()):
        raise ValueError("该时刻涉及夏令时重复或不存在，请用户明确 UTC 偏移或选择其他时刻")
    return {"datetime": result.isoformat(), "date": target.isoformat(), "timezone": timezone_name or result.tzname()}

