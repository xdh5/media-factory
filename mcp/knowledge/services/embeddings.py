"""兼容 Embeddings 协议的向量化服务，不调用文本生成接口。"""

from __future__ import annotations

import math
from collections.abc import Callable

import requests
from langchain_core.embeddings import Embeddings

from ..config import EmbeddingProfile


class CompatibleEmbeddings(Embeddings):
    """使用配置指定的完整 Embeddings 地址。"""

    def __init__(self, profile: EmbeddingProfile):
        self.profile = profile

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        profile = self.profile
        key = profile.api_key()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        for offset in range(0, len(texts), profile.batch_size):
            batch = texts[offset:offset + profile.batch_size]
            if any(not text.strip() for text in batch):
                raise ValueError("Embedding 输入不得为空")
            payload = {"model": profile.model, "input": batch, "encoding_format": "float"}
            if profile.request_dimensions:
                payload["dimensions"] = profile.dimensions
            try:
                response = requests.post(profile.endpoint, headers=headers, json=payload,
                                         timeout=profile.timeout_seconds, allow_redirects=False)
            except requests.RequestException:
                raise RuntimeError("Embedding 请求未完成，请检查服务网络与配置") from None
            if response.status_code != 200:
                raise RuntimeError(f"Embedding 服务返回 HTTP {response.status_code}")
            try:
                body = response.json()
                rows = body["data"]
                if len(rows) != len(batch) or {row["index"] for row in rows} != set(range(len(batch))):
                    raise ValueError("Embedding 响应顺序或数量不完整")
                for row in sorted(rows, key=lambda item: item["index"]):
                    vector = row["embedding"]
                    if len(vector) != profile.dimensions or any(
                        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                        for value in vector
                    ):
                        raise ValueError("Embedding 响应向量维度或数值不合法")
                    if not any(vector):
                        raise ValueError("Embedding 服务返回零向量")
                    vectors.append(vector)
            except (KeyError, TypeError, ValueError):
                raise RuntimeError("Embedding 响应格式、顺序、维度或数值不符合配置") from None
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_PROVIDERS: dict[str, Callable[[EmbeddingProfile], Embeddings]] = {"openai-compatible": CompatibleEmbeddings}


def register_embedding_provider(name: str, factory: Callable[[EmbeddingProfile], Embeddings]) -> None:
    """由项目代码注册适配器，不从外部配置动态导入任意代码。"""
    if name in _PROVIDERS:
        raise ValueError(f"Embedding 提供者已注册：{name}")
    _PROVIDERS[name] = factory


def create_embeddings(profile: EmbeddingProfile) -> Embeddings:
    if profile.provider not in _PROVIDERS:
        raise ValueError(f"未注册 Embedding 提供者：{profile.provider}")
    return _PROVIDERS[profile.provider](profile)
