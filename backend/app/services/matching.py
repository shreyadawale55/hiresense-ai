"""Hybrid semantic + structured matching logic for resume screening."""

from __future__ import annotations

import math
from typing import Any, Mapping

from app.services.embeddings import get_embedding_service, semantic_similarity
from app.services.fairness import confidence_from_signal_counts
from app.services.parsing import SKILL_VOCABULARY


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _education_rank(level: str | None) -> int:
    if not level:
        return -1
    lowered = level.lower()
    if "phd" in lowered or "doctor" in lowered:
        return 4
    if "master" in lowered or "mba" in lowered:
        return 3
    if "bachelor" in lowered or "b.tech" in lowered or "b.e." in lowered:
        return 2
    if "associate" in lowered or "diploma" in lowered:
        return 1
    if "school" in lowered:
        return 0
    return -1


def _score_experience(resume_years: float, required_years: int) -> float:
    if required_years <= 0:
        return 100.0
    ratio = max(0.0, resume_years / required_years)
    if ratio >= 1.0:
        return min(100.0, 80.0 + min(20.0, (ratio - 1.0) * 10.0))
    return max(0.0, ratio * 80.0)


def _score_education(resume_edu: str | None, required_edu: str | None) -> float:
    if not required_edu:
        return 100.0
    resume_rank = _education_rank(resume_edu)
    required_rank = _education_rank(required_edu)
    if resume_rank >= required_rank:
        return 100.0
    if resume_rank < 0:
        return 40.0
    return max(40.0, 100.0 - (required_rank - resume_rank) * 25.0)


def _score_skills(resume_skills: list[str], required: list[str], preferred: list[str]) -> tuple[float, list[str], list[str], list[str]]:
    resume_lower = {skill.lower() for skill in resume_skills}
    matched = [skill for skill in required if skill.lower() in resume_lower]
    missing = [skill for skill in required if skill.lower() not in resume_lower]
    bonus = [skill for skill in preferred if skill.lower() in resume_lower and skill.lower() not in {s.lower() for s in required}]
    match_ratio = len(matched) / max(len(required), 1)
    skill_score = min(100.0, match_ratio * 100.0 + min(12.0, len(bonus) * 2.5))
    return skill_score, matched, missing, bonus


def _job_document(job: Any) -> str:
    parts = [
        str(_get_value(job, "title", "")),
        str(_get_value(job, "company", "")),
        str(_get_value(job, "description", "")),
        str(_get_value(job, "requirements", "")),
        "Required skills: " + ", ".join(_get_value(job, "required_skills", []) or []),
        "Preferred skills: " + ", ".join(_get_value(job, "preferred_skills", []) or []),
    ]
    return " | ".join(part for part in parts if part).strip()


def _resume_document(resume_profile: Mapping[str, Any]) -> str:
    summary = str(resume_profile.get("semantic_summary") or "")
    if summary:
        return summary
    parts = [
        str(resume_profile.get("candidate_name", "")),
        str(resume_profile.get("candidate_location", "")),
        "Skills: " + ", ".join(resume_profile.get("extracted_skills", []) or []),
        "Certifications: " + ", ".join(resume_profile.get("certifications", []) or []),
        "Projects: " + "; ".join(item.get("detail", "") for item in resume_profile.get("projects", []) or []),
        "Experience: " + "; ".join(item.get("detail", "") for item in resume_profile.get("extracted_experience", []) or []),
        str(resume_profile.get("raw_text", "")[:2400]),
    ]
    return " | ".join(part for part in parts if part).strip()


def _normalize_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def score_resume_against_job(job: Any, resume_profile: Mapping[str, Any], *, semantic_hint: str | None = None) -> dict[str, Any]:
    """Compute a hybrid score and an explainability payload."""
    required_skills = [str(skill) for skill in (_get_value(job, "required_skills", []) or [])]
    preferred_skills = [str(skill) for skill in (_get_value(job, "preferred_skills", []) or [])]
    required_years = int(_get_value(job, "experience_years_min", 0) or 0)
    required_education = _get_value(job, "education_level", "") or ""

    resume_skills = [str(skill) for skill in (resume_profile.get("extracted_skills", []) or [])]
    resume_years = float(resume_profile.get("years_of_experience", 0.0) or 0.0)
    resume_education = str(resume_profile.get("education_level", "") or "")

    skill_score, matched, missing, bonus = _score_skills(resume_skills, required_skills, preferred_skills)
    experience_score = _score_experience(resume_years, required_years)
    education_score = _score_education(resume_education, required_education)

    job_document = semantic_hint or _job_document(job)
    resume_document = _resume_document(resume_profile)
    semantic_percent = round(semantic_similarity(job_document, resume_document) * 100.0, 2)

    certification_bonus = min(8.0, len(resume_profile.get("certifications", []) or []) * 1.5)
    project_bonus = min(8.0, len(resume_profile.get("projects", []) or []) * 1.2)
    semantic_bonus = min(6.0, semantic_percent * 0.06)

    overall_score = round(
        0.38 * semantic_percent
        + 0.28 * skill_score
        + 0.18 * experience_score
        + 0.10 * education_score
        + certification_bonus
        + project_bonus
        + semantic_bonus,
        2,
    )
    overall_score = min(100.0, overall_score)

    if overall_score >= 82:
        recommendation = "strong_yes"
    elif overall_score >= 68:
        recommendation = "yes"
    elif overall_score >= 48:
        recommendation = "maybe"
    else:
        recommendation = "no"

    candidate_flags = len(matched) + len(bonus) + len(resume_profile.get("projects", []) or [])
    confidence_score = confidence_from_signal_counts(
        matched_skills=len(matched),
        missing_skills=len(missing),
        timeline_items=len(resume_profile.get("experience_timeline", []) or []),
        projects=len(resume_profile.get("projects", []) or []),
    )
    confidence_score = round(min(1.0, confidence_score + min(0.1, semantic_percent / 1000.0)), 3)

    matched_str = ", ".join(matched[:5]) if matched else "no required skills"
    missing_str = ", ".join(missing[:5]) if missing else "no major skill gaps"

    explanation = (
        f"This candidate scores {overall_score:.1f}/100 for the {str(_get_value(job, 'title', 'role'))} role.\n\n"
        f"Strongest signals: {matched_str}. "
        f"Key development areas: {missing_str}.\n\n"
        f"The semantic fit is {semantic_percent:.1f}/100 and the recommendation is based on skills, "
        f"experience, education, projects, and certifications."
    )

    job_text = _job_document(job)
    resume_text = _resume_document(resume_profile)

    return {
        "overall_score": _normalize_score(overall_score),
        "skill_match_score": _normalize_score(skill_score),
        "experience_score": _normalize_score(experience_score),
        "education_score": _normalize_score(education_score),
        "semantic_score": _normalize_score(semantic_percent),
        "confidence_score": round(confidence_score, 3),
        "matched_skills": matched,
        "missing_skills": missing,
        "bonus_skills": bonus,
        "recommendation": recommendation,
        "explanation": explanation,
        "strengths": [
            *(f"Matched skill: {skill}" for skill in matched[:3]),
            *(f"Project signal: {project.get('detail', '')}" for project in (resume_profile.get("projects", []) or [])[:2]),
        ],
        "concerns": [
            *(f"Missing skill: {skill}" for skill in missing[:3]),
            *(["Experience depth could be stronger"] if experience_score < 70 else []),
        ],
        "fairness_flags": [],
        "bias_detected": False,
        "fairness_score": 100.0,
        "status": "explained",
        "candidate_name": resume_profile.get("candidate_name"),
        "candidate_email": resume_profile.get("candidate_email"),
        "candidate_location": resume_profile.get("candidate_location"),
        "years_of_experience": resume_years,
        "education_level": resume_education,
        "semantic_context": {
            "job_document": job_text[:3000],
            "resume_document": resume_text[:3000],
        },
    }


def build_query_document(query: str) -> str:
    """Normalize recruiter natural-language queries into a searchable document."""
    lowered = query.lower()
    detected = [skill for skill in SKILL_VOCABULARY if skill in lowered]
    parts = [query]
    if detected:
        parts.append("Detected skills: " + ", ".join(detected))
    return " | ".join(parts)

