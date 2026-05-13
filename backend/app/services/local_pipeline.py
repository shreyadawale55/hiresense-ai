"""Compatibility wrapper around the upgraded parsing/matching pipeline.

This module keeps the existing route and worker imports stable while the
implementation now lives in focused service modules.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.fairness import build_fairness_report, sanitize_biased_text
from app.services.matching import score_resume_against_job
from app.services.parsing import (
    parse_resume_file as _parse_resume_file,
)
from app.services.rag import build_rag_payload
from app.services.vector_store import index_job, index_resume


def parse_resume_file(file_path: str) -> dict[str, Any]:
    """Parse a resume and return a structured profile."""
    parsed = _parse_resume_file(file_path)
    if parsed.get("raw_text"):
        parsed["raw_text"] = sanitize_biased_text(parsed["raw_text"])
    return parsed


def _ensure_resume_index(resume_profile: Mapping[str, Any]) -> None:
    resume_id = resume_profile.get("id") or resume_profile.get("resume_id")
    if not resume_id:
        return
    text = resume_profile.get("semantic_summary") or resume_profile.get("raw_text", "")
    metadata = {
        "candidate_name": resume_profile.get("candidate_name"),
        "candidate_email": resume_profile.get("candidate_email"),
        "candidate_location": resume_profile.get("candidate_location"),
        "skills": resume_profile.get("extracted_skills", []),
        "education_level": resume_profile.get("education_level"),
    }
    index_resume(str(resume_id), text, metadata)


def _ensure_job_index(job: Any) -> None:
    job_id = getattr(job, "id", None) or getattr(job, "job_id", None)
    if not job_id:
        return
    text = " | ".join(
        part
        for part in [
            getattr(job, "title", ""),
            getattr(job, "company", ""),
            getattr(job, "description", ""),
            getattr(job, "requirements", ""),
            ", ".join(getattr(job, "required_skills", []) or []),
            ", ".join(getattr(job, "preferred_skills", []) or []),
        ]
        if part
    )
    metadata = {
        "title": getattr(job, "title", None),
        "company": getattr(job, "company", None),
        "required_skills": getattr(job, "required_skills", []) or [],
    }
    index_job(str(job_id), text, metadata)


def build_screening_result(job: Any, resume_profile: Mapping[str, Any]) -> dict[str, Any]:
    """Score a parsed resume against a job posting."""
    _ensure_job_index(job)
    _ensure_resume_index(resume_profile)
    result = score_resume_against_job(job, resume_profile)
    fairness_report = build_fairness_report(result.get("explanation", ""))
    result["fairness_flags"] = result.get("fairness_flags") or fairness_report["bias_keywords"]
    result["bias_keywords"] = fairness_report["bias_keywords"]
    result["bias_detected"] = bool(result.get("fairness_flags"))
    result["fairness_score"] = fairness_report.get("fairness_score")
    result["status"] = "explained"
    rag_payload = build_rag_payload(job, resume_profile, result)
    result["retrieved_context"] = rag_payload.get("retrieved_context", [])
    result["explanation_context"] = rag_payload
    result["score_breakdown"] = {
        "overall": result.get("overall_score", 0),
        "semantic": result.get("semantic_score", 0),
        "skills": result.get("skill_match_score", 0),
        "experience": result.get("experience_score", 0),
        "education": result.get("education_score", 0),
        "confidence": result.get("confidence_score", 0),
    }
    return result


def score_resume_profile(job: Any, resume_profile: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for the screening route."""
    return build_screening_result(job, resume_profile)


__all__ = [
    "parse_resume_file",
    "build_screening_result",
    "score_resume_profile",
]
