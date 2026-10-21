"""日志及知识入库前脱敏，不处理业务原始配置文件。"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

SENSITIVE = re.compile(r"(?i)(api.?key|token|secret|password|authorization|cookie|credential)")


def redact(value):
    if isinstance(value, dict):
        return {str(key): "[已脱敏]" if SENSITIVE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    for name, secret in os.environ.items():
        if SENSITIVE.search(name) and len(secret) >= 6:
            value = value.replace(secret, "[已脱敏]")
    value = re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [已脱敏]", value)
    value = re.sub(r"(?i)((?:[\w-]*(?:api[_-]?key|token|password|secret|cookie)[\w-]*|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;}]+", r"\1[已脱敏]", value)
    value = re.sub(r"(?i)([?&](?:[\w-]*(?:key|token|sig|signature|auth|credential)[\w-]*|x-amz-[\w-]+|Sec-MS-GEC|ConnectionId|code|state)=)[^&\s'\"]+", r"\1[已脱敏]", value)
    value = re.sub(r"https?://[^/\s:@]+:[^/\s@]+@", "https://[已脱敏]@", value)
    value = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16})\b", "[已脱敏]", value)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[邮箱已脱敏]", value)
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", value)
    value = re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+", r"C:/Users/[用户]", value)
    return value
