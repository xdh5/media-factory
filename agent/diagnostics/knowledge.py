"""使用 LangGraph 原生向量存储检索故障资料。"""

from contextlib import asynccontextmanager
import hashlib
import os

from dotenv import load_dotenv
from langchain_core.tools import ToolException, tool
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.store.base import PutOp
from langgraph.store.sqlite import AsyncSqliteStore
from langsmith import traceable
from openai import APIError

from ..settings import ROOT, llm_configuration


DOCUMENTS = ("diagnostic-documents",)
PASSAGES = ("diagnostic-passages",)


class KnowledgeBase:
    def __init__(self, database):
        self.database = database.with_suffix(".knowledge.sqlite")

    @asynccontextmanager
    async def store(self, indexed=False):
        index = None
        if indexed:
            load_dotenv(ROOT / ".env")
            api_key = os.getenv("AGENT_EMBEDDING_API_KEY")
            base_url = os.getenv("AGENT_EMBEDDING_BASE_URL")
            base = llm_configuration() if not (api_key and base_url) else {}
            embeddings = OpenAIEmbeddings(
                api_key=api_key or base["api_key"],
                base_url=(base_url or base["base_url"]).rstrip("/"),
                model=os.getenv("AGENT_EMBEDDING_MODEL", "text-embedding-v3"),
                check_embedding_ctx_length=False, chunk_size=8,
                request_timeout=float(os.getenv("AGENT_DIAGNOSTIC_TIMEOUT", "180")),
                max_retries=0,
            )
            index = {"dims": int(os.getenv("AGENT_EMBEDDING_DIMENSIONS", "1024")),
                     "embed": embeddings, "fields": ["content"]}
        async with AsyncSqliteStore.from_conn_string(str(self.database), index=index) as store:
            await store.setup()
            yield store

    async def ingest(self, source, text, kind="document", evidence=""):
        if kind == "solution" and not evidence.strip():
            raise ValueError("长期解决方案必须包含人工核验依据")
        if not text.strip():
            raise ValueError("知识内容不能为空")
        identity = hashlib.sha256((source + "\n" + text).encode()).hexdigest()
        async with self.store(indexed=True) as store:
            if not await store.aget(DOCUMENTS, identity):
                await store.abatch(self.document_operations(identity, {
                    "source": source, "kind": kind, "evidence": evidence, "content": text,
                }))
        return identity

    @staticmethod
    def document_operations(identity, document):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200, chunk_overlap=180, separators=["\n\n", "\n", "。", " ", ""])
        passages = splitter.split_text(document["content"])
        return [PutOp(DOCUMENTS, identity, document, index=False), *[
            PutOp(PASSAGES, f"{identity}:{index}", {**document, "content": passage})
            for index, passage in enumerate(passages)
        ]]

    @traceable(name="故障资料语义检索", run_type="retriever")
    async def search(self, query, k=5):
        async with self.store() as store:
            if not await store.asearch(DOCUMENTS, limit=1):
                return []
        async with self.store(indexed=True) as store:
            results = await store.asearch(PASSAGES, query=query, limit=k)
        return [{"id": item.key, **item.value, "score": item.score} for item in results]

    async def documents(self, store):
        offset = 0
        while batch := await store.asearch(DOCUMENTS, limit=100, offset=offset):
            for item in batch:
                yield item
            offset += len(batch)

    async def list_documents(self):
        async with self.store() as store:
            return [{"id": item.key, "created": item.created_at.isoformat(), **{
                key: item.value[key] for key in ("source", "kind", "evidence")
            }} async for item in self.documents(store)]

    async def reindex(self):
        async with self.store(indexed=True) as store:
            documents = [item async for item in self.documents(store)]
            count = 0
            for item in documents:
                operations = self.document_operations(item.key, item.value)[1:]
                await store.abatch(operations)
                count += len(operations)
        return {"reindexed_chunks": count}


def diagnostic_search_tool(database):
    @tool
    async def agent_search_diagnostics(query: str) -> list[dict]:
        """用简短故障描述或实际报错检索项目资料，返回匹配片段及来源。"""
        try:
            return await KnowledgeBase(database).search(query, k=4)
        except (APIError, ValueError) as exc:
            raise ToolException(f"故障资料检索失败：{exc}") from exc

    agent_search_diagnostics.handle_tool_error = True
    return agent_search_diagnostics
