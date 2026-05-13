"""Schemas for semantic search and recruiter natural-language queries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from app.schemas.screening import CandidateSimilarityResponse


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    job_id: Optional[uuid.UUID] = None


class NaturalLanguageSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    include_fairness: bool = True


class SemanticSearchResult(BaseModel):
    query: str
    total: int
    items: List[CandidateSimilarityResponse]
    metadata: Dict[str, Any] = Field(default_factory=dict)

