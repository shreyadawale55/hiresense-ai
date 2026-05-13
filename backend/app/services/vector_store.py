"""Lightweight vector search service with optional FAISS support."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.core.config import DATA_DIR, settings
from app.services.embeddings import get_embedding_service

try:  # Optional heavy dependency
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional import
    np = None

try:  # Optional heavy dependency
    import faiss  # type: ignore
except Exception:  # pragma: no cover - optional import
    faiss = None


@dataclass
class VectorRecord:
    id: str
    kind: str
    text: str
    vector: list[float]
    metadata: dict[str, Any]


def _dot(lhs: Iterable[float], rhs: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(lhs, rhs))


def _norm(vec: Iterable[float]) -> float:
    return math.sqrt(sum(value * value for value in vec))


def _cosine(lhs: list[float], rhs: list[float]) -> float:
    denom = _norm(lhs) * _norm(rhs)
    if not denom:
        return 0.0
    return max(0.0, min(1.0, _dot(lhs, rhs) / denom))


class VectorStore:
    """Persistence-friendly semantic index for jobs and resumes."""

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.index_path = Path(settings.VECTOR_INDEX_PATH)
        self.metadata_path = Path(settings.VECTOR_METADATA_PATH)
        self.records: dict[str, VectorRecord] = {}
        self.kind_index: dict[str, set[str]] = {"resume": set(), "job": set()}
        self._faiss_index = None
        self._faiss_ids: list[str] = []
        self._load()

    @property
    def backend(self) -> str:
        return "faiss" if self._faiss_index is not None else "memory"

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        try:
            data = json.loads(self.metadata_path.read_text())
            for item in data.get("records", []):
                record = VectorRecord(
                    id=item["id"],
                    kind=item["kind"],
                    text=item.get("text", ""),
                    vector=[float(x) for x in item.get("vector", [])],
                    metadata=item.get("metadata", {}),
                )
                self.records[record.id] = record
                self.kind_index.setdefault(record.kind, set()).add(record.id)
            if faiss is not None and np is not None and self.records:
                self._rebuild_faiss()
        except Exception:
            self.records = {}
            self.kind_index = {"resume": set(), "job": set()}

    def _save(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"records": [asdict(record) for record in self.records.values()]}
        self.metadata_path.write_text(json.dumps(data, indent=2))
        if self._faiss_index is not None and faiss is not None:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._faiss_index, str(self.index_path))

    def _rebuild_faiss(self) -> None:
        if faiss is None or np is None or not self.records:
            self._faiss_index = None
            self._faiss_ids = []
            return
        vectors = [record.vector for record in self.records.values()]
        matrix = np.array(vectors, dtype="float32")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        self._faiss_index = index
        self._faiss_ids = list(self.records.keys())

    def _maybe_rebuild_faiss(self) -> None:
        if faiss is None or np is None:
            return
        try:
            self._rebuild_faiss()
        except Exception:
            self._faiss_index = None
            self._faiss_ids = []

    def upsert(self, *, kind: str, item_id: str, text: str, metadata: dict[str, Any] | None = None) -> VectorRecord:
        vector = self.embedding_service.embed(text)
        record = VectorRecord(
            id=str(item_id),
            kind=kind,
            text=text,
            vector=vector,
            metadata=metadata or {},
        )
        self.records[record.id] = record
        self.kind_index.setdefault(kind, set()).add(record.id)
        self._maybe_rebuild_faiss()
        self._save()
        return record

    def get(self, item_id: str) -> VectorRecord | None:
        return self.records.get(str(item_id))

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        limit: int = 10,
        exclude_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query_vector = self.embedding_service.embed(query)
        candidate_ids = list(self.records.keys())
        if kind:
            candidate_ids = [record_id for record_id in candidate_ids if self.records[record_id].kind == kind]
        if exclude_id:
            candidate_ids = [record_id for record_id in candidate_ids if record_id != exclude_id]
        if not candidate_ids:
            return []

        if self._faiss_index is not None and faiss is not None and np is not None:
            matrix = np.array([query_vector], dtype="float32")
            faiss.normalize_L2(matrix)
            distances, indices = self._faiss_index.search(matrix, min(limit * 2, len(self._faiss_ids)))
            results: list[dict[str, Any]] = []
            for score, idx in zip(distances[0], indices[0]):
                if idx < 0:
                    continue
                record_id = self._faiss_ids[idx]
                if record_id not in candidate_ids:
                    continue
                record = self.records[record_id]
                if exclude_id and record_id == exclude_id:
                    continue
                results.append(
                    {
                        "id": record.id,
                        "kind": record.kind,
                        "score": round(float(score), 4),
                        "text": record.text,
                        "metadata": record.metadata,
                    }
                )
                if len(results) >= limit:
                    break
            return results

        results = []
        for record_id in candidate_ids:
            record = self.records[record_id]
            score = _cosine(query_vector, record.vector)
            results.append(
                {
                    "id": record.id,
                    "kind": record.kind,
                    "score": round(score, 4),
                    "text": record.text,
                    "metadata": record.metadata,
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def similar(self, item_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        record = self.get(item_id)
        if not record:
            return []
        return self.search(record.text, kind=record.kind, limit=limit, exclude_id=record.id)

    def delete(self, item_id: str) -> None:
        record = self.records.pop(str(item_id), None)
        if not record:
            return
        kind_set = self.kind_index.get(record.kind)
        if kind_set and record.id in kind_set:
            kind_set.remove(record.id)
        self._maybe_rebuild_faiss()
        self._save()

    def rebuild_from_records(self, records: list[dict[str, Any]]) -> None:
        self.records = {}
        self.kind_index = {"resume": set(), "job": set()}
        for item in records:
            self.records[item["id"]] = VectorRecord(
                id=item["id"],
                kind=item["kind"],
                text=item.get("text", ""),
                vector=[float(x) for x in item.get("vector", [])],
                metadata=item.get("metadata", {}),
            )
            self.kind_index.setdefault(item["kind"], set()).add(item["id"])
        self._maybe_rebuild_faiss()
        self._save()


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return VectorStore()


def index_resume(resume_id: str, text: str, metadata: dict[str, Any] | None = None) -> VectorRecord:
    return get_vector_store().upsert(kind="resume", item_id=resume_id, text=text, metadata=metadata)


def index_job(job_id: str, text: str, metadata: dict[str, Any] | None = None) -> VectorRecord:
    return get_vector_store().upsert(kind="job", item_id=job_id, text=text, metadata=metadata)


def search_candidates(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    return get_vector_store().search(query, kind="resume", limit=limit)


def similar_resumes(resume_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    return get_vector_store().similar(resume_id, limit=limit)


def delete_vector_item(item_id: str) -> None:
    get_vector_store().delete(item_id)
