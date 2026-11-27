"""确定性文本规范化、指纹与可追溯中文切片。"""

from __future__ import annotations

import hashlib
import json
import unicodedata

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import EmbeddingProfile


def normalize_text(text: str) -> str:
    """保留代码缩进及段落，只统一 Unicode、换行和首尾空白。"""
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def document_fingerprint(knowledge_base: str, content: str, metadata: dict) -> str:
    """分类及正文相同的同库新增使用同一指纹。"""
    value = {"knowledge_base": knowledge_base, "content": normalize_text(content), "metadata": metadata}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def split_document(knowledge_base: str, document_id: str, revision: int, content: str,
                   metadata: dict, profile: EmbeddingProfile) -> list[Document]:
    """片段位置相对于规范化后的权威原文，ID 可用于幂等向量写入。"""
    text = normalize_text(content)
    if not text:
        raise ValueError("知识正文不能为空")
    if revision < 1:
        raise ValueError("知识版本必须为正整数")
    reserved = {"knowledge_base", "document_id", "revision", "profile_id", "chunk_id", "chunk_index", "start_index", "end_index"}
    if reserved.intersection(metadata):
        raise ValueError("业务元数据不能覆盖系统片段字段")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=profile.chunk_size, chunk_overlap=profile.chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        keep_separator="end", add_start_index=True,
    )
    documents = splitter.create_documents([text], metadatas=[metadata])
    for index, document in enumerate(documents):
        start = document.metadata["start_index"]
        if start < 0 or text[start:start + len(document.page_content)] != document.page_content:
            raise ValueError("切片原文位置校验失败")
        identity = json.dumps([knowledge_base, document_id, revision, profile.profile_id, index], ensure_ascii=False)
        document.metadata.update(
            knowledge_base=knowledge_base, document_id=document_id, revision=revision,
            profile_id=profile.profile_id, chunk_index=index,
            chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            end_index=start + len(document.page_content),
        )
    return documents
