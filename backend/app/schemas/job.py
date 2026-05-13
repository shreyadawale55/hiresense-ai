"""Pydantic schemas for Job API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class JobBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255, example="Senior Data Engineer")
    company: str = Field(..., min_length=2, max_length=255, example="TechCorp Inc.")
    description: str = Field(..., min_length=50)
    requirements: str = Field(..., min_length=20)
    required_skills: List[str] = Field(default_factory=list, example=["Python", "SQL", "Apache Spark"])
    preferred_skills: List[str] = Field(default_factory=list, example=["Kubernetes", "dbt"])
    experience_years_min: int = Field(default=0, ge=0, le=30)
    experience_years_max: int = Field(default=10, ge=0, le=50)
    education_level: Optional[str] = Field(None, example="Bachelor's in Computer Science")
    location: Optional[str] = Field(None, example="Remote / Bangalore, India")
    salary_min: Optional[float] = Field(None, ge=0)
    salary_max: Optional[float] = Field(None, ge=0)
    job_type: str = Field(default="full-time", example="full-time")
    diversity_goal: bool = Field(default=False, description="SDG 8: Enable diversity screening flag")
    semantic_summary: Optional[str] = None


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    status: Optional[JobStatus] = None
    diversity_goal: Optional[bool] = None
    semantic_summary: Optional[str] = None


class JobResponse(JobBase):
    id: uuid.UUID
    created_by_id: Optional[uuid.UUID] = None
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    screening_count: Optional[int] = 0
    search_document: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    items: List[JobResponse]
    total: int
    page: int
    page_size: int
