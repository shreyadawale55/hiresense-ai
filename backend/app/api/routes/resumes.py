"""API routes for resume upload, parsing, and retrieval."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.resume import Resume
from app.schemas.resume import ResumeListResponse, ResumeResponse, ResumeUploadResponse
from app.services.local_pipeline import parse_resume_file
from app.services.vector_store import delete_vector_item, index_resume

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _apply_parsed_resume(resume: Resume, parsed: dict) -> None:
    resume.candidate_name = parsed.get("candidate_name")
    resume.candidate_email = parsed.get("candidate_email")
    resume.candidate_phone = parsed.get("candidate_phone")
    resume.candidate_location = parsed.get("candidate_location")
    resume.emails = parsed.get("emails", [])
    resume.phones = parsed.get("phones", [])
    resume.github_url = parsed.get("github_url")
    resume.linkedin_url = parsed.get("linkedin_url")
    resume.raw_text = parsed.get("raw_text")
    resume.extracted_skills = parsed.get("extracted_skills", [])
    resume.extracted_education = parsed.get("extracted_education", [])
    resume.extracted_experience = parsed.get("extracted_experience", [])
    resume.certifications = parsed.get("certifications", [])
    resume.projects = parsed.get("projects", [])
    resume.experience_timeline = parsed.get("experience_timeline", [])
    resume.years_of_experience = parsed.get("years_of_experience", 0.0)
    resume.education_level = parsed.get("education_level")
    resume.semantic_summary = parsed.get("semantic_summary")
    resume.parse_confidence = parsed.get("parse_confidence", 0.0)
    resume.parse_status = parsed.get("parse_status", "done")
    resume.parse_error = None


def _resume_search_document(resume: Resume) -> str:
    parts = [
        resume.semantic_summary or "",
        resume.candidate_name or "",
        resume.candidate_location or "",
        ", ".join(resume.extracted_skills or []),
        ", ".join(resume.certifications or []),
        "; ".join(project.get("detail", "") for project in (resume.projects or [])[:3]),
    ]
    return " | ".join(part for part in parts if part)


async def _persist_and_index_resume(db: AsyncSession, resume: Resume) -> None:
    await db.flush()
    await db.refresh(resume)
    index_resume(
        str(resume.id),
        _resume_search_document(resume) or resume.raw_text or resume.file_name,
        {
            "candidate_name": resume.candidate_name,
            "candidate_email": resume.candidate_email,
            "candidate_location": resume.candidate_location,
            "skills": resume.extracted_skills or [],
            "education_level": resume.education_level,
        },
    )


async def _parse_locally(resume: Resume, file_path: str, db: AsyncSession) -> None:
    parsed = parse_resume_file(file_path)
    _apply_parsed_resume(resume, parsed)
    resume.parse_status = "done"
    await _persist_and_index_resume(db, resume)


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    file: UploadFile = File(..., description="PDF or DOCX resume file"),
    job_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Upload a resume file. Processing happens asynchronously via Celery."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Use PDF or DOCX.",
        )

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.1f}MB. Max: {settings.MAX_FILE_SIZE_MB}MB",
        )

    file_ext = ALLOWED_CONTENT_TYPES[file.content_type]
    file_id = uuid.uuid4()
    file_name = f"{file_id}.{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_name)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    async with aiofiles.open(file_path, "wb") as handle:
        await handle.write(content)

    resume = Resume(
        id=file_id,
        file_name=file.filename or file_name,
        file_path=file_path,
        file_type=file_ext,
        file_size_bytes=len(content),
        parse_status="pending",
        parse_confidence=0.0,
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    parse_task_id = None
    try:
        from workers.tasks.resume_parser import parse_resume_task

        task = parse_resume_task.apply_async(
            args=[str(resume.id), file_path],
            queue="default",
        )
        resume.parse_status = "processing"
        parse_task_id = task.id
        await db.flush()
    except Exception:
        await _parse_locally(resume, file_path, db)

    return ResumeUploadResponse(
        id=resume.id,
        file_name=resume.file_name,
        file_type=resume.file_type,
        parse_status=resume.parse_status,
        parse_task_id=parse_task_id,
        parse_confidence=resume.parse_confidence or 0.0,
    )


@router.post("/upload-batch", status_code=status.HTTP_202_ACCEPTED)
async def upload_batch_resumes(
    files: list[UploadFile] = File(...),
    job_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Upload multiple resumes at once (max 50)."""
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Max 50 files per batch.")

    results = []
    for file in files:
        try:
            result = await upload_resume(file=file, job_id=job_id, db=db, current_user=current_user)
            results.append({"file": file.filename, "status": "accepted", "id": str(result.id)})
        except HTTPException as exc:
            results.append({"file": file.filename, "status": "error", "detail": exc.detail})

    return {"uploaded": len(results), "results": results}


@router.get("/", response_model=ResumeListResponse)
async def list_resumes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    parse_status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List resumes."""
    query = select(Resume)
    if parse_status:
        query = query.where(Resume.parse_status == parse_status)
    if search:
        query = query.where(
            or_(
                Resume.candidate_name.ilike(f"%{search}%"),
                Resume.candidate_email.ilike(f"%{search}%"),
                Resume.github_url.ilike(f"%{search}%"),
                Resume.linkedin_url.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    query = query.order_by(Resume.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    resumes = result.scalars().all()

    return ResumeListResponse(items=resumes, total=total, page=page, page_size=page_size)


@router.get("/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a specific resume by ID."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Delete a resume and its file."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.file_path and os.path.exists(resume.file_path):
        os.remove(resume.file_path)

    await db.delete(resume)
    try:
        delete_vector_item(str(resume.id))
    except Exception:
        pass
