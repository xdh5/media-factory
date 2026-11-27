"""独立 RAG 流程：原文、切片、向量化、同步与检索。"""

from __future__ import annotations

import json

from tools.database._errors import DatabaseConflictError, DatabaseError

from ..config import EmbeddingProfile, KnowledgeSettings
from ..infrastructure.data_api import knowledge_request as request
from ..schemas import KnowledgeDocumentInput, PublisherExperience
from .embeddings import create_embeddings
from .text_processing import document_fingerprint, normalize_text, split_document


class KnowledgeService:
    """仅向量化操作需要模型配置，原文与状态操作独立可用。"""

    def __init__(self, settings: KnowledgeSettings | None = None):
        self._settings = settings

    @property
    def settings(self) -> KnowledgeSettings:
        if self._settings is None:
            self._settings = KnowledgeSettings.from_environment()
        return self._settings

    def _profile_by_id(self, identity: str) -> EmbeddingProfile:
        for profile in self.settings.profiles.values():
            if profile.profile_id == identity:
                return profile
        raise ValueError(f"本机缺少 profile 配置：{identity}")

    def _base(self, knowledge_base: str) -> dict:
        for base in request("bases")["bases"]:
            if base["id"] == knowledge_base:
                return base
        raise ValueError(f"知识库不存在：{knowledge_base}")

    @staticmethod
    def _public_profile(profile: EmbeddingProfile) -> dict:
        return profile.model_dump(exclude={"api_key_env", "credential_file_env", "timeout_seconds", "batch_size"})

    def list_bases(self) -> dict:
        return request("bases")

    def register_base(self, knowledge_base: str, kind: str, profile_name: str) -> dict:
        profile = self.settings.profile(profile_name)
        return request("register", knowledge_base=knowledge_base, kind=kind,
                       profile_id=profile.profile_id, profile=self._public_profile(profile))

    def _document_body(self, knowledge_base: str, title: str, content: str, metadata: dict) -> dict:
        value = KnowledgeDocumentInput(title=title, content=normalize_text(content), metadata=metadata)
        if self._base(knowledge_base)["kind"] == "publisher-errors":
            value.metadata = PublisherExperience.model_validate(metadata).model_dump(mode="json")
        if len(json.dumps(value.metadata, ensure_ascii=False)) > 12000:
            raise ValueError("元数据不能超过 12000 字符")
        reserved = {"knowledge_base", "document_id", "revision", "profile_id", "chunk_id", "chunk_index", "start_index", "end_index"}
        if reserved.intersection(value.metadata):
            raise ValueError("元数据不能覆盖系统片段字段")
        return {"knowledge_base": knowledge_base, **value.model_dump(),
                "fingerprint": document_fingerprint(knowledge_base, value.content, value.metadata)}

    def add(self, knowledge_base: str, title: str, content: str, metadata: dict) -> dict:
        return request("add", **self._document_body(knowledge_base, title, content, metadata))

    def update(self, knowledge_base: str, document_id: str, expected_revision: int,
               title: str, content: str, metadata: dict) -> dict:
        return request("update", document_id=document_id, expected_revision=expected_revision,
                       **self._document_body(knowledge_base, title, content, metadata))

    def get(self, knowledge_base: str, document_id: str) -> dict:
        return request("get", knowledge_base=knowledge_base, document_id=document_id)

    def list_documents(self, knowledge_base: str, cursor: str = "", limit: int = 20) -> dict:
        return request("list", knowledge_base=knowledge_base, cursor=cursor, limit=limit)

    def delete(self, knowledge_base: str, document_id: str, expected_revision: int) -> dict:
        return request("delete", knowledge_base=knowledge_base, document_id=document_id, expected_revision=expected_revision)

    def index_status(self, knowledge_base: str, cursor: str = "", limit: int = 50) -> dict:
        return request("status", knowledge_base=knowledge_base, cursor=cursor, limit=limit)

    def reindex(self, knowledge_base: str, profile_name: str) -> dict:
        profile = self.settings.profile(profile_name)
        return request("reindex", knowledge_base=knowledge_base, profile_id=profile.profile_id,
                       profile=self._public_profile(profile))

    def activate_profile(self, knowledge_base: str, profile_name: str, expected_generation: int) -> dict:
        return request("activate", knowledge_base=knowledge_base,
                       profile_id=self.settings.profile(profile_name).profile_id, expected_generation=expected_generation)

    def sync(self, knowledge_base: str, limit: int = 5, retry_failed: bool = False) -> dict:
        if not 1 <= limit <= 20:
            raise ValueError("每次同步任务数量必须为 1 至 20")
        refreshed = request("refresh", knowledge_base=knowledge_base)
        results = []
        # 单次失败继续其他任务，但同一次调用不重复领取失败项。
        failed_ids: set[str] = set()
        for _ in range(limit):
            claim = request("claim", knowledge_base=knowledge_base, retry_failed=retry_failed, exclude_job_ids=sorted(failed_ids))
            job = claim["job"]
            if job is None:
                break
            identity = {"knowledge_base": knowledge_base, "job_id": job["id"], "lease_token": job["lease_token"]}
            try:
                document = claim["document"]
                chunks = []
                if not document["deleted"] and document["revision"] == job["revision"]:
                    profile = self._profile_by_id(job["profile_id"])
                    parts = split_document(knowledge_base, document["id"], document["revision"],
                                           document["content"], document["metadata"], profile)
                    if len(parts) > 256:
                        raise ValueError("切片数量超过 256，请使用更大的 chunk_size 创建新 profile")
                    vectors = create_embeddings(profile).embed_documents([part.page_content for part in parts])
                    chunks = [{"id": part.metadata["chunk_id"], "content": part.page_content,
                               "chunk_index": part.metadata["chunk_index"], "start_index": part.metadata["start_index"],
                               "end_index": part.metadata["end_index"], "values": vector} for part, vector in zip(parts, vectors, strict=True)]
                receipt = request("submit", **identity, chunks=chunks)
                results.append({"job_id": job["id"], **receipt})
            except (ValueError, RuntimeError, DatabaseError) as exc:
                # 上游错误只保留受控类别，不保存请求体、密钥和完整响应。
                message = str(exc)
                try:
                    request("fail", **identity, error=message[:500])
                except DatabaseConflictError:
                    message = "同步租约已失效，请恢复同步并核对索引任务"
                failed_ids.add(job["id"])
                results.append({"job_id": job["id"], "status": "failed", "error": message})
        return {"jobs": results, "visibility": refreshed, "status": self.index_status(knowledge_base)}

    def search(self, knowledge_base: str, query: str, filters: dict | None = None,
               limit: int = 5, score_threshold: float | None = None, max_per_document: int = 2) -> dict:
        query = normalize_text(query)
        if not query or len(query) > 8000 or not 1 <= limit <= 20 or not 1 <= max_per_document <= 5:
            raise ValueError("查询必须为 1 至 8000 字符，limit 为 1 至 20，每文档上限为 1 至 5")
        base = self._base(knowledge_base)
        profile = self._profile_by_id(base["active_profile"])
        vector = create_embeddings(profile).embed_query(query)
        result = request("query", knowledge_base=knowledge_base, profile_id=profile.profile_id,
                         vector=vector, filters=filters or {}, limit=min(limit * 5, 100))
        # Vectorize 的欧氏距离越小越相关，余弦和点积越大越相关。
        ascending = profile.metric == "euclidean"
        matches = sorted(result["matches"], key=lambda item: item["score"], reverse=not ascending)
        kept, counts, seen = [], {}, set()
        for item in matches:
            score = item["score"]
            if score_threshold is not None and (score > score_threshold if ascending else score < score_threshold):
                continue
            identity = (item["document_id"], item["content"])
            if identity in seen or counts.get(item["document_id"], 0) >= max_per_document:
                continue
            seen.add(identity)
            counts[item["document_id"]] = counts.get(item["document_id"], 0) + 1
            kept.append(item)
            if len(kept) == limit:
                break
        return {"knowledge_base": knowledge_base, "profile_id": profile.profile_id, "metric": profile.metric,
                "score_order": "ascending" if ascending else "descending", "matches": kept,
                "index_status": self.index_status(knowledge_base)["counts"]}
