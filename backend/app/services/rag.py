"""Retrieval-augmented generation helpers for grounded explanations."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.matching import build_query_document
from app.services.vector_store import search_candidates, similar_resumes


def retrieve_context(job: Any, resume_profile: Mapping[str, Any], *, top_k: int = 3) -> list[dict[str, Any]]:
    """Fetch grounded context for an explanation prompt."""
    query = build_query_document(
        f"{job.title} {job.company} {job.description} {job.requirements} {', '.join(job.required_skills or [])}"
    )
    retrieved = search_candidates(query, limit=top_k)
    similar = []
    resume_id = resume_profile.get("id") or resume_profile.get("resume_id")
    if resume_id:
        similar = similar_resumes(str(resume_id), limit=top_k)
    context: list[dict[str, Any]] = []
    for item in retrieved:
        context.append(
            {
                "type": "job_match",
                "id": item["id"],
                "score": item["score"],
                "metadata": item.get("metadata", {}),
            }
        )
    for item in similar:
        context.append(
            {
                "type": "similar_candidate",
                "id": item["id"],
                "score": item["score"],
                "metadata": item.get("metadata", {}),
            }
        )
    return context


def build_rag_payload(job: Any, resume_profile: Mapping[str, Any], scoring_result: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble the context used by the LLM explainer."""
    retrieved_context = retrieve_context(job, resume_profile, top_k=4)
    resume_document = resume_profile.get("semantic_summary") or resume_profile.get("raw_text", "")[:2400]
    job_document = (
        f"{job.title} | {job.company} | {job.description[:1200]} | {job.requirements[:1200]}"
        if hasattr(job, "description")
        else str(job)
    )
    return {
        "job_title": getattr(job, "title", scoring_result.get("job_title", "")),
        "job_description": getattr(job, "description", scoring_result.get("job_description", "")),
        "resume_text_snippet": resume_document[:2500],
        "job_context": job_document[:2500],
        "retrieved_context": retrieved_context,
        "overall_score": scoring_result.get("overall_score", 0),
        "skill_match_score": scoring_result.get("skill_match_score", 0),
        "experience_score": scoring_result.get("experience_score", 0),
        "education_score": scoring_result.get("education_score", 0),
        "semantic_score": scoring_result.get("semantic_score", 0),
        "confidence_score": scoring_result.get("confidence_score", 0),
        "matched_skills": scoring_result.get("matched_skills", []),
        "missing_skills": scoring_result.get("missing_skills", []),
        "bonus_skills": scoring_result.get("bonus_skills", []),
        "candidate_skills": resume_profile.get("extracted_skills", []),
        "years_of_experience": resume_profile.get("years_of_experience", 0),
        "education_level": resume_profile.get("education_level", ""),
        "development_opportunities": scoring_result.get("missing_skills", [])[:5],
    }


def build_grounded_prompt(payload: Mapping[str, Any]) -> str:
    """Prompt the LLM with only verified facts."""
    retrieved = payload.get("retrieved_context", []) or []
    retrieved_lines = []
    for item in retrieved[:8]:
        metadata = item.get("metadata", {})
        source = metadata.get("candidate_name") or metadata.get("title") or item.get("id")
        retrieved_lines.append(f"- {item.get('type')}: {source} (score={item.get('score')})")

    retrieved_block = "\n".join(retrieved_lines) if retrieved_lines else "- No external retrieval context available"
    return f"""You are HireSense AI, an impartial hiring assistant aligned with SDG 8.

Use only the verified context below. Do not invent facts, do not infer protected attributes, and do not mention demographics.

JOB CONTEXT:
Title: {payload.get('job_title')}
Description: {payload.get('job_description')}

RESUME CONTEXT:
Semantic summary: {payload.get('resume_text_snippet')}

NUMERIC SCORES:
Overall: {payload.get('overall_score')}/100
Semantic: {payload.get('semantic_score')}/100
Skills: {payload.get('skill_match_score')}/100
Experience: {payload.get('experience_score')}/100
Education: {payload.get('education_score')}/100
Confidence: {payload.get('confidence_score')}

RETRIEVED CONTEXT:
{retrieved_block}

Return JSON only with:
{{
  "recommendation": "strong_yes | yes | maybe | no",
  "explanation": "A grounded hiring explanation using only the provided evidence.",
  "strengths": ["..."],
  "concerns": ["..."],
  "development_opportunities": ["..."],
  "interview_questions": ["..."],
  "sdg8_note": "..."
}}"""

