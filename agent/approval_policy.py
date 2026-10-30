"""统一审批扩展入口，当前不启用人工审批。"""

APPROVAL_REQUIRED_TOOLS: frozenset[str] = frozenset()


def policy_instruction() -> str:
    if APPROVAL_REQUIRED_TOOLS:
        return "审批由宿主策略执行，仅在宿主实际中断时等待人工确认。"
    return "当前工具审批关闭。根据用户任务直接调用工具，不要求用户再次批准、同意或确认执行；缺少业务信息时才询问。"
