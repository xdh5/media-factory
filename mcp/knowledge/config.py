"""知识库向量配置；凭据只在调用时从指定环境变量读取。"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmbeddingProfile(BaseModel):
    """不同模型、端点或切片策略对应不同配置版本。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(ge=1, le=1536)
    index_name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    credential_file_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    metric: Literal["cosine", "euclidean", "dot-product"] = "cosine"
    chunk_size: int = Field(default=800, ge=64, le=8000)
    chunk_overlap: int = Field(default=120, ge=0)
    splitter_version: Literal["recursive-zh-v1"] = "recursive-zh-v1"
    request_dimensions: bool = True
    batch_size: int = Field(default=8, ge=1, le=100)
    timeout_seconds: float = Field(default=60, gt=0, le=300)

    @model_validator(mode="after")
    def validate_profile(self) -> EmbeddingProfile:
        if self.api_key_env and self.credential_file_env:
            raise ValueError("凭据只能选择环境变量或显式 Wrangler OAuth 文件之一")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Embedding 端点必须是无内嵌凭据的 HTTP 地址")
        if parsed.query or parsed.fragment:
            raise ValueError("Embedding 端点不能携带查询参数或片段")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("远程 Embedding 端点必须使用 HTTPS")
        return self

    @property
    def profile_id(self) -> str:
        """模型、索引和切片语义相同才共享配置标识。"""
        fields = self.model_dump(exclude={"api_key_env", "credential_file_env", "batch_size", "timeout_seconds"})
        return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]

    def api_key(self) -> str | None:
        if self.credential_file_env:
            filename = os.getenv(self.credential_file_env, "").strip()
            if not filename:
                raise ValueError(f"缺少凭据文件路径环境变量：{self.credential_file_env}")
            value = tomllib.loads(Path(filename).read_text(encoding="utf-8"))
            expires = value.get("expiration_time")
            if expires and datetime.fromisoformat(str(expires)) <= datetime.now(UTC):
                raise ValueError("Wrangler OAuth 已过期，请执行 wrangler whoami 刷新授权或改用 AI API Token")
            token = value.get("oauth_token", "").strip()
            if not token:
                raise ValueError("指定凭据文件缺少 Wrangler OAuth 授权")
            return token
        if self.api_key_env is None:
            return None
        value = os.getenv(self.api_key_env, "").strip()
        if not value:
            raise ValueError(f"缺少 Embedding 凭据环境变量：{self.api_key_env}")
        return value


class KnowledgeSettings(BaseModel):
    """配置文件只包含模型和索引描述，不包含密钥值。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    profiles: dict[str, EmbeddingProfile] = Field(min_length=1)

    @classmethod
    def from_environment(cls) -> KnowledgeSettings:
        filename = os.getenv("MEDIA_FACTORY_KNOWLEDGE_CONFIG", "").strip()
        if not filename:
            raise ValueError("缺少配置：MEDIA_FACTORY_KNOWLEDGE_CONFIG")
        return cls.model_validate_json(Path(filename).read_text(encoding="utf-8"))

    def profile(self, name: str) -> EmbeddingProfile:
        if name not in self.profiles:
            raise ValueError(f"未配置 Embedding profile：{name}")
        return self.profiles[name]
