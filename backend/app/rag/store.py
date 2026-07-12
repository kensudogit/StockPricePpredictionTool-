"""RAG store: pgvector primary, with adapters for Pinecone/Weaviate/Milvus/Qdrant."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

DIM = 384


def embed_text(text_in: str, dim: int = DIM) -> list[float]:
    """Deterministic hashing embedder (no external model required).

    Replace with OpenAI/local sentence-transformers in production.
    """
    tokens = re.findall(r"\w+", text_in.lower())
    vec = np.zeros(dim, dtype=np.float32)
    if not tokens:
        return vec.tolist()
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.tolist()


class PgVectorStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self,
        *,
        doc_type: str,
        content: str,
        title: str | None = None,
        symbol_id: int | None = None,
        source_ref: str | None = None,
        meta: dict | None = None,
    ) -> int:
        emb = embed_text(content)
        emb_lit = "[" + ",".join(f"{x:.8f}" for x in emb) + "]"
        result = await self.db.execute(
            text(
                """
                INSERT INTO rag_documents (doc_type, symbol_id, title, content, source_ref, meta, embedding)
                VALUES (:doc_type, :symbol_id, :title, :content, :source_ref, CAST(:meta AS jsonb), CAST(:embedding AS vector))
                RETURNING id
                """
            ),
            {
                "doc_type": doc_type,
                "symbol_id": symbol_id,
                "title": title,
                "content": content,
                "source_ref": source_ref,
                "meta": __import__("json").dumps(meta or {}),
                "embedding": emb_lit,
            },
        )
        await self.db.commit()
        return int(result.scalar_one())

    async def search(self, query: str, limit: int = 5, doc_type: str | None = None) -> list[dict[str, Any]]:
        emb = embed_text(query)
        emb_lit = "[" + ",".join(f"{x:.8f}" for x in emb) + "]"
        sql = """
            SELECT id, doc_type, title, content, source_ref, meta,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM rag_documents
            WHERE embedding IS NOT NULL
        """
        params: dict[str, Any] = {"embedding": emb_lit, "limit": limit}
        if doc_type:
            sql += " AND doc_type = :doc_type"
            params["doc_type"] = doc_type
        sql += " ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"
        rows = (await self.db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]


class ExternalVectorAdapter:
    """Thin stubs for commercial vector DBs."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        self.settings = get_settings()

    async def upsert(self, **kwargs) -> dict:
        return {"backend": self.backend, "status": "stub", "note": "Configure API keys to enable"}

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        return [{"backend": self.backend, "query": query, "status": "stub"}]


def get_vector_store(db: AsyncSession, backend: str | None = None):
    backend = backend or get_settings().vector_backend
    if backend == "pgvector":
        return PgVectorStore(db)
    return ExternalVectorAdapter(backend)


class RAGService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.store = PgVectorStore(db)

    async def ingest_text(
        self,
        content: str,
        doc_type: str,
        title: str | None = None,
        symbol_id: int | None = None,
        source_ref: str | None = None,
    ) -> dict:
        # chunk by paragraphs ~800 chars
        chunks = []
        buf = ""
        for para in content.split("\n"):
            if len(buf) + len(para) > 800 and buf:
                chunks.append(buf.strip())
                buf = para
            else:
                buf += "\n" + para
        if buf.strip():
            chunks.append(buf.strip())
        ids = []
        for i, ch in enumerate(chunks):
            doc_id = await self.store.upsert(
                doc_type=doc_type,
                content=ch,
                title=f"{title or doc_type}#{i}",
                symbol_id=symbol_id,
                source_ref=source_ref,
            )
            ids.append(doc_id)
        return {"chunks": len(ids), "ids": ids}

    async def query(self, question: str, limit: int = 5) -> dict:
        hits = await self.store.search(question, limit=limit)
        context = "\n\n".join(f"- {h.get('title')}: {h.get('content')}" for h in hits)
        return {"hits": hits, "context": context}
