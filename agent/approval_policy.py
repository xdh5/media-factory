"""统一审批扩展入口，当前不启用人工审批。"""

APPROVAL_REQUIRED_TOOLS: frozenset[str] = frozenset()


def policy_instruction() -> str:
    if APPROVAL_REQUIRED_TOOLS:
        return "审批由宿主策略执行，仅在宿主实际中断时等待人工确认。"
    return "按用户授权调用工具，缺必要业务信息时询问。"
