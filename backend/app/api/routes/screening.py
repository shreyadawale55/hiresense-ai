"""API routes for AI screening operations and semantic candidate search."""

from __future__ import annotations

import uuid
from typing import Optional

from celery import chain
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.job import Job
from app.models.resume import Resume
from app.models.screening import Screening
from app.schemas.search import NaturalLanguageSearchRequest, SemanticSearchRequest
from app.schemas.screening import (
    AIExplanation,
    CandidateSimilarityResponse,
    ScoreBreakdown,
    SearchResponse,
    ScreeningCreateRequest,
    ScreeningListResponse,
    ScreeningResponse,
)
from app.services.local_pipeline import build_screening_result, parse_resume_file, score_resume_profile
from app.services.rag import build_rag_payload
from app.services.realtime import publish_screening_event
from app.services.vector_store import search_candidates, similar_resumes

router = APIRouter()


def _ensure_job_access(job: Job, user) -> None:
    if user.role.value == "admin":
        return
    if job.created_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this job")


def _apply_screening_result(screening: Screening, result: dict) -> None:
    screening.overall_score = result.get("overall_score")
    screening.skill_match_score = result.get("skill_match_score")
    screening.experience_score = result.get("experience_score")
    screening.education_score = result.get("education_score")
    screening.semantic_score = result.get("semantic_score")
    screening.confidence_score = result.get("confidence_score")
    screening.matched_skills = result.get("matched_skills", [])
    screening.missing_skills = result.get("missing_skills", [])
    screening.bonus_skills = result.get("bonus_skills", [])
    screening.score_breakdown = result.get("score_breakdown", {})
    screening.ai_explanation = result.get("explanation")
    screening.ai_recommendation = result.get("recommendation")
    screening.ai_strengths = result.get("strengths", [])
    screening.ai_concerns = result.get("concerns", [])
    screening.retrieved_context = result.get("retrieved_context", [])
    screening.explanation_context = result.get("explanation_context", {})
    screening.llm_model = result.get("llm_model")
    screening.fairness_flags = result.get("fairness_flags", [])
    screening.bias_keywords = result.get("bias_keywords", [])
    screening.bias_detected = result.get("bias_detected", False)
    screening.fairness_score = result.get("fairness_score")
    screening.status = result.get("status", "explained")
    screening.score_task_id = result.get("score_task_id")
    screening.explain_task_id = result.get("explain_task_id")
    screening.query_text = result.get("query_text", screening.query_text)


def _resume_profile(resume: Resume) -> dict:
    if resume.raw_text and resume.extracted_skills:
        return {
            "id": str(resume.id),
            "raw_text": resume.raw_text or "",
            "candidate_name": resume.candidate_name,
            "candidate_email": resume.candidate_email,
            "candidate_phone": resume.candidate_phone,
            "candidate_location": resume.candidate_location,
            "emails": resume.emails or [],
            "phones": resume.phones or [],
            "github_url": resume.github_url,
            "linkedin_url": resume.linkedin_url,
            "extracted_skills": resume.extracted_skills or [],
            "extracted_education": resume.extracted_education or [],
            "extracted_experience": resume.extracted_experience or [],
            "certifications": resume.certifications or [],
            "projects": resume.projects or [],
            "experience_timeline": resume.experience_timeline or [],
            "years_of_experience": resume.years_of_experience or 0.0,
            "education_level": resume.education_level or "",
            "semantic_summary": resume.semantic_summary or "",
            "parse_confidence": resume.parse_confidence or 0.0,
            "parse_status": resume.parse_status,
        }

    parsed = parse_resume_file(resume.file_path)
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
    return {
        "id": str(resume.id),
        **parsed,
    }


def _build_screening_response(s: Screening, resume: Resume) -> ScreeningResponse:
    return ScreeningResponse(
        id=s.id,
        job_id=s.job_id,
        resume_id=s.resume_id,
        status=s.status,
        rank=s.rank,
        query_text=s.query_text,
        score=ScoreBreakdown(
            overall_score=s.overall_score,
            skill_match_score=s.skill_match_score,
            experience_score=s.experience_score,
            education_score=s.education_score,
            semantic_score=s.semantic_score,
            confidence_score=s.confidence_score,
            matched_skills=s.matched_skills or [],
            missing_skills=s.missing_skills or [],
            bonus_skills=s.bonus_skills or [],
            fairness_score=s.fairness_score,
            score_breakdown=s.score_breakdown or {},
        ),
        ai=AIExplanation(
            explanation=s.ai_explanation,
            recommendation=s.ai_recommendation,
            strengths=s.ai_strengths or [],
            concerns=s.ai_concerns or [],
            development_opportunities=(s.explanation_context or {}).get("development_opportunities", []),
            interview_questions=(s.explanation_context or {}).get("interview_questions", []),
            sdg8_note=(s.explanation_context or {}).get("sdg8_note"),
            fairness_flags=s.fairness_flags or [],
            bias_detected=s.bias_detected,
            bias_keywords=s.bias_keywords or [],
            llm_model=s.llm_model,
        ),
        candidate_name=resume.candidate_name if resume else None,
        candidate_email=resume.candidate_email if resume else None,
        candidate_location=resume.candidate_location if resume else None,
        retrieved_context=s.retrieved_context or [],
        explanation_context=s.explanation_context or {},
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


async def _load_job(job_id: uuid.UUID, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def start_screening(
    payload: ScreeningCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("recruiter", "admin")),
):
    """Kick off AI screening for one job against multiple resumes."""
    job = await _load_job(payload.job_id, db)
    _ensure_job_access(job, current_user)

    created = []
    for resume_id in payload.resume_ids:
        res_result = await db.execute(select(Resume).where(Resume.id == resume_id))
        resume = res_result.scalar_one_or_none()
        if not resume:
            continue

        dup = await db.execute(
            select(Screening).where(
                Screening.job_id == payload.job_id,
                Screening.resume_id == resume_id,
            )
        )
        if dup.scalar_one_or_none():
            continue

        screening = Screening(
            job_id=payload.job_id,
            resume_id=resume_id,
            status="pending",
            query_text=payload.query_text or job.search_document or job.title,
        )
        db.add(screening)
        await db.flush()
        await db.refresh(screening)

        profile = _resume_profile(resume)
        local_result = build_screening_result(job, profile)
        rag_payload = build_rag_payload(job, profile, local_result)
        local_result.update(
            {
                "retrieved_context": rag_payload.get("retrieved_context", []),
                "explanation_context": rag_payload,
                "query_text": screening.query_text,
            }
        )
        _apply_screening_result(screening, local_result)

        try:
            from workers.tasks.ai_scorer import score_resume_task
            from workers.tasks.llm_explainer import explain_resume_task

            task_chain = chain(
                score_resume_task.s(str(screening.id), str(payload.job_id), str(resume_id)),
                explain_resume_task.s(str(screening.id)),
            ).apply_async(queue="ai_scoring")
            screening.score_task_id = task_chain.id
            screening.status = "processing"
        except Exception:
            screening.status = "explained"

        created.append(str(screening.id))

        await publish_screening_event(
            str(payload.job_id),
            "screening.created",
            {
                "screening_id": str(screening.id),
                "resume_id": str(resume_id),
                "status": screening.status,
                "candidate_name": resume.candidate_name,
            },
        )

    return {
        "message": f"Screening started for {len(created)} resumes",
        "job_id": str(payload.job_id),
        "screening_ids": created,
    }


@router.get("/{job_id}/results", response_model=ScreeningListResponse)
async def get_screening_results(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get ranked screening results for a job."""
    job = await _load_job(job_id, db)
    _ensure_job_access(job, current_user)

    screenings_result = await db.execute(
        select(Screening)
        .where(Screening.job_id == job_id)
        .order_by(Screening.overall_score.desc().nullslast())
    )
    screenings = screenings_result.scalars().all()

    responses = []
    for idx, screening in enumerate(screenings, start=1):
        res_result = await db.execute(select(Resume).where(Resume.id == screening.resume_id))
        resume = res_result.scalar_one_or_none()
        response = _build_screening_response(screening, resume)
        response.rank = idx
        responses.append(response)

    return ScreeningListResponse(
        job_id=job_id,
        job_title=job.title,
        items=responses,
        total=len(responses),
    )


@router.get("/result/{screening_id}", response_model=ScreeningResponse)
async def get_single_screening(
    screening_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a single screening result by ID."""
    s_result = await db.execute(select(Screening).where(Screening.id == screening_id))
    screening = s_result.scalar_one_or_none()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    job = await _load_job(screening.job_id, db)
    _ensure_job_access(job, current_user)

    res_result = await db.execute(select(Resume).where(Resume.id == screening.resume_id))
    resume = res_result.scalar_one_or_none()

    return _build_screening_response(screening, resume)


@router.get("/stats/{job_id}")
async def get_screening_stats(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get aggregate statistics for a job's screening."""
    job = await _load_job(job_id, db)
    _ensure_job_access(job, current_user)

    result = await db.execute(
        select(
            func.count(Screening.id).label("total"),
            func.avg(Screening.overall_score).label("avg_score"),
            func.avg(Screening.semantic_score).label("avg_semantic_score"),
            func.avg(Screening.confidence_score).label("avg_confidence_score"),
            func.max(Screening.overall_score).label("max_score"),
            func.min(Screening.overall_score).label("min_score"),
            func.coalesce(
                func.sum(case((Screening.status == "explained", 1), else_=0)),
                0,
            ).label("completed"),
        ).where(Screening.job_id == job_id)
    )
    row = result.first()
    if not row:
        return {"total": 0, "avg_score": None, "max_score": None, "min_score": None, "completed": 0}
    return {
        "total": row.total,
        "avg_score": round(float(row.avg_score or 0), 2) if row.avg_score is not None else None,
        "avg_semantic_score": round(float(row.avg_semantic_score or 0), 2) if row.avg_semantic_score is not None else None,
        "avg_confidence_score": round(float(row.avg_confidence_score or 0), 3) if row.avg_confidence_score is not None else None,
        "max_score": row.max_score,
        "min_score": row.min_score,
        "completed": row.completed,
    }


@router.get("/similarity/{resume_id}", response_model=list[CandidateSimilarityResponse])
async def similarity_search(
    resume_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Find candidates similar to a specific resume."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    hits = similar_resumes(str(resume_id), limit=limit)
    responses: list[CandidateSimilarityResponse] = []
    for rank, item in enumerate(hits, start=1):
        hit_resume = await db.execute(select(Resume).where(Resume.id == uuid.UUID(item["id"])))
        record = hit_resume.scalar_one_or_none()
        responses.append(
            CandidateSimilarityResponse(
                resume_id=uuid.UUID(item["id"]),
                candidate_name=record.candidate_name if record else item.get("metadata", {}).get("candidate_name"),
                similarity=round(item["score"] * 100.0, 2),
                rank=rank,
                reason="Semantic similarity in skills, projects, and experience",
                metadata=item.get("metadata", {}),
            )
        )
    return responses


@router.post("/search", response_model=SearchResponse)
async def natural_language_search(
    payload: NaturalLanguageSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recruiter natural-language candidate search."""
    query = payload.query
    hits = search_candidates(query, limit=payload.limit)
    responses: list[CandidateSimilarityResponse] = []
    for rank, item in enumerate(hits, start=1):
        hit_resume = await db.execute(select(Resume).where(Resume.id == uuid.UUID(item["id"])))
        record = hit_resume.scalar_one_or_none()
        metadata = item.get("metadata", {})
        responses.append(
            CandidateSimilarityResponse(
                resume_id=uuid.UUID(item["id"]),
                candidate_name=record.candidate_name if record else metadata.get("candidate_name"),
                similarity=round(item["score"] * 100.0, 2),
                rank=rank,
                reason=f"Matched query terms against candidate profile: {payload.query}",
                metadata=metadata,
            )
        )
    return SearchResponse(query=payload.query, total=len(responses), items=responses, metadata={"include_fairness": payload.include_fairness})
