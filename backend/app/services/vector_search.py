"""Compatibility layer for the legacy vector search API.

The production code now uses :mod:`app.services.vector_store`, which supports
semantic indexing for both resumes and jobs with optional FAISS persistence.
This module keeps the older worker-facing API intact so background tasks can
continue to call ``get_vector_service().add_resume(...)`` without needing to
know about the newer implementation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.vector_store import (
    delete_vector_item,
    get_vector_store,
    index_resume,
    search_candidates,
    similar_resumes,
)

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Backwards-compatible facade over the production vector store."""

    def add_resume(
        self,
        resume_id: str,
        text: str,
        metadata: Dict[str, Any],
        embedding: Optional[Any] = None,
    ) -> None:
        # The production store computes embeddings internally, so the optional
        # precomputed embedding parameter is accepted only for API parity.
        index_resume(resume_id, text, metadata)

    def search_resumes(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # ``where`` and ``where_document`` are retained for compatibility. The
        # underlying store currently supports semantic search without these
        # filters, which is sufficient for the current application paths.
        results = search_candidates(query, limit=n_results)
        return {
            "query": query,
            "results": [
                {
                    "resume_id": item["id"],
                    "score": item["score"],
                    "metadata": item.get("metadata", {}),
                    "document": item.get("text", "")[:500] + ("..." if len(item.get("text", "")) > 500 else ""),
                }
                for item in results
            ],
            "total_found": len(results),
        }

    def find_similar_candidates(
        self,
        resume_id: str,
        n_results: int = 5,
        exclude_self: bool = True,
    ) -> List[Dict[str, Any]]:
        results = similar_resumes(resume_id, limit=n_results + (1 if exclude_self else 0))
        similar: List[Dict[str, Any]] = []
        for item in results:
            if exclude_self and item["id"] == resume_id:
                continue
            similar.append(
                {
                    "resume_id": item["id"],
                    "similarity_score": item["score"],
                    "metadata": item.get("metadata", {}),
                }
            )
            if len(similar) >= n_results:
                break
        return similar

    def get_resume_context(self, resume_ids: List[str]) -> str:
        store = get_vector_store()
        context_parts: List[str] = []
        for resume_id in resume_ids:
            record = store.get(resume_id)
            if not record:
                continue
            metadata = record.metadata or {}
            context_parts.append(
                f"""Candidate: {metadata.get('candidate_name', 'Unknown')}
Experience: {metadata.get('experience_years', 'N/A')} years
Skills: {metadata.get('skills', 'N/A')}
Education: {metadata.get('education_level', 'N/A')}

Resume Text:
{record.text}

---
"""
            )
        return "\n".join(context_parts)

    def delete_resume(self, resume_id: str) -> None:
        delete_vector_item(resume_id)

    def get_stats(self) -> Dict[str, Any]:
        store = get_vector_store()
        return {
            "total_resumes": len([record for record in store.records.values() if record.kind == "resume"]),
            "embedding_model": store.embedding_service.model_name,
            "embedding_dim": store.embedding_service.dimension,
            "collection_name": "vector_store",
            "backend": store.backend,
        }


_vector_service: Optional[VectorSearchService] = None


def get_vector_service() -> VectorSearchService:
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorSearchService()
    return _vector_service


async def warm_vector_store() -> None:
    stats = get_vector_service().get_stats()
    logger.info("Vector store warmed up", extra=stats)
