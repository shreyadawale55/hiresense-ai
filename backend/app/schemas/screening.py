"""Pydantic schemas for screening, similarity, and explainability."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScreeningCreateRequest(BaseModel):
    job_id: uuid.UUID
    resume_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    query_text: Optional[str] = None


class ScoreBreakdown(BaseModel):
    overall_score: Optional[float] = None
    skill_match_score: Optional[float] = None
    experience_score: Optional[float] = None
    education_score: Optional[float] = None
    semantic_score: Optional[float] = None
    confidence_score: Optional[float] = None
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    bonus_skills: List[str] = Field(default_factory=list)
    fairness_score: Optional[float] = None
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)


class AIExplanation(BaseModel):
    explanation: Optional[str] = None
    recommendation: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    development_opportunities: List[str] = Field(default_factory=list)
    interview_questions: List[str] = Field(default_factory=list)
    sdg8_note: Optional[str] = None
    fairness_flags: List[str] = Field(default_factory=list)
    bias_detected: bool = False
    bias_keywords: List[str] = Field(default_factory=list)
    llm_model: Optional[str] = None


class ScreeningResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID
    status: str
    rank: Optional[int] = None
    query_text: Optional[str] = None
    score: ScoreBreakdown
    ai: AIExplanation
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    retrieved_context: List[Dict[str, Any]] = Field(default_factory=list)
    explanation_context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScreeningListResponse(BaseModel):
    job_id: uuid.UUID
    job_title: Optional[str] = None
    items: List[ScreeningResponse]
    total: int


class CandidateSimilarityResponse(BaseModel):
    resume_id: uuid.UUID
    candidate_name: Optional[str] = None
    similarity: float
    rank: int
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    total: int
    items: List[CandidateSimilarityResponse]
    metadata: Dict[str, Any] = Field(default_factory=dict)

