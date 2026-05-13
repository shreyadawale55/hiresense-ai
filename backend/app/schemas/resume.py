"""Pydantic schemas for Resume API."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResumeBase(BaseModel):
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_location: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None


class ResumeUploadResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    parse_status: str
    parse_task_id: Optional[str] = None
    message: str = "Resume uploaded successfully. Processing in background."
    parse_confidence: float = 0.0


class ResumeResponse(ResumeBase):
    id: uuid.UUID
    file_name: str
    file_type: str
    file_size_bytes: Optional[int] = None
    extracted_skills: List[str] = Field(default_factory=list)
    extracted_education: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_experience: List[Dict[str, Any]] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    experience_timeline: List[Dict[str, Any]] = Field(default_factory=list)
    years_of_experience: float = 0.0
    education_level: Optional[str] = None
    semantic_summary: Optional[str] = None
    parse_confidence: float = 0.0
    parse_status: str
    parse_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    embedding_ready: bool = False

    model_config = ConfigDict(from_attributes=True)


class ResumeListResponse(BaseModel):
    items: List[ResumeResponse]
    total: int
    page: int
    page_size: int
