"""Vector store adapters — pgvector, Pinecone, and local JSON file."""
import json
import math
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import structlog

from services.api.core.config import get_settings

logger = structlog.get_logger(__name__)

_adapter_lock = threading.Lock()
_adapter_instance: Optional["BaseVectorAdapter"] = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity — no numpy required."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class BaseVectorAdapter(ABC):
    @abstractmethod
    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None: ...

    @abstractmethod
    async def query(self, vector: list[float], top_k: int = 10) -> list[dict]: ...

    @abstractmethod
    async def delete(self, id: str) -> None: ...


class PgVectorAdapter(BaseVectorAdapter):
    """Stores embeddings using native pgvector vector(768) column.

    Uses the <=> cosine distance operator via raw SQL for similarity search.
    Results are returned as 1 - distance so higher = more similar (matches
    the interface expected by rank_jobs_task).

    Session factory: uses get_worker_session_factory() (process singleton)
    instead of creating a new engine per call to avoid connection pool flooding.
    """

    @staticmethod
    def _vec_literal(vector: list[float]) -> str:
        """Format a Python list as a pgvector literal: '[1.0,2.0,...]'."""
        return "[" + ",".join(str(v) for v in vector) + "]"

    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Embedding

        vec_str = self._vec_literal(vector)
        sf = get_worker_session_factory()
        async with sf() as session:
            existing = await session.get(Embedding, id)
            if existing:
                existing.embedding_json = vector
                existing.embedding_source = metadata.get("source", "unknown")
                existing.embedding_model = metadata.get("model", "unknown")
                # Update native vector column via raw SQL (SQLAlchemy ORM doesn't
                # know the column type — it's managed outside the model definition)
                await session.execute(
                    text("UPDATE embeddings SET embedding_vector = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": vec_str, "id": id},
                )
            else:
                emb = Embedding(
                    id=id,
                    job_id=metadata.get("job_id", id),
                    vector_id=id,
                    embedding_source=metadata.get("source", "unknown"),
                    embedding_model=metadata.get("model", "unknown"),
                    embedding_json=vector,
                )
                session.add(emb)
                try:
                    await session.flush()  # so the row exists before the UPDATE below
                except IntegrityError as exc:
                    # Race condition: the referenced job_id may have been deleted
                    # by a concurrent cleanup task between the job-existence check
                    # in generate_embedding_task and this INSERT.  Gracefully skip.
                    logger.warning(
                        "upsert_skipped_fk_violation",
                        id=id,
                        job_id=metadata.get("job_id"),
                        detail=str(exc),
                    )
                    await session.rollback()
                    return
                await session.execute(
                    text("UPDATE embeddings SET embedding_vector = CAST(:vec AS vector) WHERE id = :id"),
                    {"vec": vec_str, "id": id},
                )
            await session.commit()

    async def query(self, vector: list[float], top_k: int = 10) -> list[dict]:
        """Return top-k most similar embeddings using the native <=> operator.

        Falls back to Python cosine similarity when no rows have embedding_vector
        populated yet (i.e. the migration ran but no embeddings have been generated).
        """
        from sqlalchemy import text

        from services.api.core.database import get_worker_session_factory

        vec_str = self._vec_literal(vector)
        sf = get_worker_session_factory()
        async with sf() as session:
            # Check if any rows have the native vector column populated
            count_result = await session.execute(
                text("SELECT COUNT(*) FROM embeddings WHERE embedding_vector IS NOT NULL")
            )
            native_count = count_result.scalar() or 0

            if native_count > 0:
                # Native ANN search via HNSW index — O(log n), not O(n)
                # Use CAST(:vec AS vector) instead of :vec::vector because
                # SQLAlchemy's text() treats :name as a named parameter and
                # the double-colon causes asyncpg to fail with a syntax error.
                result = await session.execute(
                    text(
                        "SELECT id, job_id, "
                        "1 - (embedding_vector <=> CAST(:vec AS vector)) AS score "
                        "FROM embeddings "
                        "WHERE embedding_vector IS NOT NULL "
                        "ORDER BY embedding_vector <=> CAST(:vec AS vector) "
                        "LIMIT :k"
                    ),
                    {"vec": vec_str, "k": top_k},
                )
                return [{"id": row.id, "job_id": row.job_id, "score": row.score} for row in result]
            else:
                # No native vectors yet — fall back to Python cosine similarity
                # on embedding_json until embeddings are regenerated.
                from sqlalchemy import select
                from services.api.models.db import Embedding

                result = await session.execute(select(Embedding))
                embeddings = result.scalars().all()

        scored = []
        for emb in embeddings:
            if emb.embedding_json:
                score = cosine_similarity(vector, emb.embedding_json)
                scored.append({"id": emb.id, "job_id": emb.job_id, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    async def delete(self, id: str) -> None:
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Embedding

        sf = get_worker_session_factory()
        async with sf() as session:
            emb = await session.get(Embedding, id)
            if emb:
                await session.delete(emb)
                await session.commit()


class PineconeAdapter(BaseVectorAdapter):
    """Pinecone vector database adapter."""

    def __init__(self) -> None:
        from pinecone import Pinecone

        settings = get_settings()
        pc = Pinecone(api_key=settings.pinecone_api_key)
        self._index = pc.Index(settings.pinecone_index)
        logger.info("vector_adapter_init", provider="pinecone", index=settings.pinecone_index)

    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None:
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._index.upsert(vectors=[(id, vector, metadata)]))

    async def query(self, vector: list[float], top_k: int = 10) -> list[dict]:
        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: self._index.query(vector=vector, top_k=top_k, include_metadata=True)
        )
        return [
            {"id": m["id"], "job_id": m.get("metadata", {}).get("job_id", m["id"]), "score": m["score"]}
            for m in result.get("matches", [])
        ]

    async def delete(self, id: str) -> None:
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._index.delete(ids=[id]))


class LocalVectorAdapter(BaseVectorAdapter):
    """JSON file-based vector store — for development/testing with no external dependencies."""

    def __init__(self, path: str = "/tmp/jobhunter_vectors.json") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._store: dict[str, dict] = {}
        self._load()
        logger.info("vector_adapter_init", provider="local", path=str(self._path))

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._store = json.load(f)
            except Exception:
                self._store = {}

    def _save(self) -> None:
        with open(self._path, "w") as f:
            json.dump(self._store, f)

    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None:
        with self._lock:
            self._store[id] = {"vector": vector, "metadata": metadata}
            self._save()

    async def query(self, vector: list[float], top_k: int = 10) -> list[dict]:
        with self._lock:
            scored = []
            for id_, data in self._store.items():
                score = cosine_similarity(vector, data["vector"])
                scored.append({
                    "id": id_,
                    "job_id": data["metadata"].get("job_id", id_),
                    "score": score,
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    async def delete(self, id: str) -> None:
        with self._lock:
            self._store.pop(id, None)
            self._save()


def get_vector_adapter() -> BaseVectorAdapter:
    """Singleton factory — returns adapter based on VECTOR_DB_PROVIDER env var."""
    global _adapter_instance
    if _adapter_instance is None:
        with _adapter_lock:
            if _adapter_instance is None:
                settings = get_settings()
                if settings.vector_db_provider == "pgvector":
                    _adapter_instance = PgVectorAdapter()
                elif settings.vector_db_provider == "pinecone":
                    _adapter_instance = PineconeAdapter()
                else:
                    _adapter_instance = LocalVectorAdapter()
    return _adapter_instance
