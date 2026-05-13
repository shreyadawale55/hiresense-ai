"""API routes for Job management."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.job import Job, JobStatus
from app.schemas.job import JobCreate, JobListResponse, JobResponse, JobUpdate
from app.services.vector_store import delete_vector_item, index_job

router = APIRouter()


def _compose_job_document(job: Job | JobCreate) -> str:
    parts = [
        getattr(job, "title", ""),
        getattr(job, "company", ""),
        getattr(job, "description", ""),
        getattr(job, "requirements", ""),
        "Required skills: " + ", ".join(getattr(job, "required_skills", []) or []),
        "Preferred skills: " + ", ".join(getattr(job, "preferred_skills", []) or []),
        f"Experience: {getattr(job, 'experience_years_min', 0)}-{getattr(job, 'experience_years_max', 0)} years",
        f"Education: {getattr(job, 'education_level', '') or 'any'}",
        f"Location: {getattr(job, 'location', '') or 'any'}",
    ]
    return " | ".join(part for part in parts if part)


async def _load_job_or_404(job_id: uuid.UUID, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _ensure_job_access(job: Job, user) -> None:
    current_role = getattr(user.role, "value", user.role)
    if current_role == "admin":
        return
    if job.created_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this job")


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Create a new job posting."""
    job = Job(
        **payload.model_dump(),
        created_by_id=current_user.id,
    )
    job.search_document = _compose_job_document(job)
    job.semantic_summary = payload.semantic_summary or job.search_document
    db.add(job)
    await db.flush()
    await db.refresh(job)
    index_job(
        str(job.id),
        job.search_document or job.semantic_summary or "",
        {
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills or [],
            "created_by_id": str(job.created_by_id) if job.created_by_id else None,
        },
    )
    return job


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[JobStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all job postings with pagination and optional filtering."""
    query = select(Job)
    if getattr(current_user.role, "value", current_user.role) != "admin":
        query = query.where(Job.created_by_id == current_user.id)
    if status:
        query = query.where(Job.status == status)
    if search:
        query = query.where(
            or_(
                Job.title.ilike(f"%{search}%"),
                Job.company.ilike(f"%{search}%"),
                Job.description.ilike(f"%{search}%"),
                Job.requirements.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(items=jobs, total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    """Get a specific job by ID."""
    job = await _load_job_or_404(job_id, db)
    _ensure_job_access(job, current_user)
    return job


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Update a job posting."""
    job = await _load_job_or_404(job_id, db)
    _ensure_job_access(job, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    job.search_document = _compose_job_document(job)
    if not job.semantic_summary:
        job.semantic_summary = job.search_document
    await db.flush()
    await db.refresh(job)
    index_job(
        str(job.id),
        job.search_document or job.semantic_summary or "",
        {
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills or [],
            "created_by_id": str(job.created_by_id) if job.created_by_id else None,
        },
    )
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Delete a job posting."""
    job = await _load_job_or_404(job_id, db)
    _ensure_job_access(job, current_user)
    await db.delete(job)
    try:
        delete_vector_item(str(job.id))
    except Exception:
        pass
