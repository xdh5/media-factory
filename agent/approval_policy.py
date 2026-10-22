"""统一审批扩展入口，当前不启用人工审批。"""

APPROVAL_REQUIRED_TOOLS: frozenset[str] = frozenset()


def requires_approval(tool_name: str, arguments: dict, read_only: bool) -> bool:
    """以后需要审批时在此配置工具或增加参数条件。"""
    return not read_only and tool_name in APPROVAL_REQUIRED_TOOLS


def policy_instruction() -> str:
    if APPROVAL_REQUIRED_TOOLS:
        return "审批由宿主策略执行，仅在宿主实际中断时等待人工确认。"
    return "当前工具审批关闭。根据用户任务直接调用工具，不要求用户再次批准、同意或确认执行；缺少业务信息时才询问。"
