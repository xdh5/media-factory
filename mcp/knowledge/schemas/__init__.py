"""知识原文与已验证发布经验输入约束。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerificationEvidence(BaseModel):
    """代码版本可作为附加说明，成功依据必须是实际业务观察。"""

    model_config = ConfigDict(extra="forbid")
    type: Literal["receipt", "observation", "log"]
    reference: str = Field(min_length=1, max_length=4000)


class PublisherExperience(BaseModel):
    """证据真实性由宿主负责，服务只校验必要结构。"""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    business_line: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    platform: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    stage: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    verified: Literal[True]
    error_summary: str = Field(min_length=1, max_length=4000)
    root_cause: str = Field(min_length=1, max_length=4000)
    solution_steps: list[str] = Field(min_length=1, max_length=50)
    applicability: str = Field(min_length=1, max_length=4000)
    verified_at: datetime
    evidence: list[VerificationEvidence] = Field(min_length=1, max_length=30)

    @field_validator("verified_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("验证时间必须包含时区")
        return value

    @field_validator("solution_steps")
    @classmethod
    def steps_are_nonempty(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("解决步骤不能为空")
        return values


class KnowledgeDocumentInput(BaseModel):
    """写入前规范化并校验，元数据不替代系统版本字段。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100000)
    metadata: dict = Field(default_factory=dict)
