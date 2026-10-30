"""在聊天界面与框架原生中断格式之间转换。"""


def interrupt_payload(value):
    if "action_requests" in value:
        return {"kind": "approval", **value}
    return value


def resume_value(interruption, response):
    if "action_requests" in interruption and isinstance(response, dict) and "approved" in response:
        return {"decisions": [{"type": "approve" if response["approved"] is True else "reject"}
                              for _ in interruption["action_requests"]]}
    return response
