"""Startup bootstrap helpers for seeding and cache warm-up."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User, UserRole
from app.services.vector_store import get_vector_store


async def ensure_initial_admin(db: AsyncSession) -> User | None:
    """Create a bootstrap admin if the database is empty."""
    result = await db.execute(select(User))
    existing = result.scalars().first()
    if existing:
        return existing

    admin = User(
        email=settings.INITIAL_ADMIN_EMAIL,
        full_name=settings.INITIAL_ADMIN_FULL_NAME,
        role=UserRole.ADMIN,
        hashed_password=hash_password(settings.INITIAL_ADMIN_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db.add(admin)
    await db.flush()
    return admin


async def warm_vector_store(db: AsyncSession) -> dict[str, int]:
    """Index jobs and resumes into the vector store for semantic search."""
    indexed = {"jobs": 0, "resumes": 0}
    records: list[dict[str, Any]] = []

    jobs = (await db.execute(select(Job))).scalars().all()
    resumes = (await db.execute(select(Resume))).scalars().all()

    for job in jobs:
        text = " | ".join(
            part
            for part in [
                job.title,
                job.company,
                job.description,
                job.requirements,
                "Required skills: " + ", ".join(job.required_skills or []),
                "Preferred skills: " + ", ".join(job.preferred_skills or []),
            ]
            if part
        )
        records.append(
            {
                "id": str(job.id),
                "kind": "job",
                "text": text,
                "vector": get_vector_store().embedding_service.embed(text),
                "metadata": {
                    "title": job.title,
                    "company": job.company,
                    "required_skills": job.required_skills or [],
                },
            }
        )
        indexed["jobs"] += 1

    for resume in resumes:
        text = resume.semantic_summary or resume.raw_text or resume.file_name
        records.append(
            {
                "id": str(resume.id),
                "kind": "resume",
                "text": text,
                "vector": get_vector_store().embedding_service.embed(text),
                "metadata": {
                    "candidate_name": resume.candidate_name,
                    "candidate_email": resume.candidate_email,
                    "candidate_location": resume.candidate_location,
                    "skills": resume.extracted_skills or [],
                },
            }
        )
        indexed["resumes"] += 1

    get_vector_store().rebuild_from_records(records)
    return indexed
