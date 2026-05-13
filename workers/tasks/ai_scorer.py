"""
HireSense AI — Celery Task: AI Scorer
Calls the PyTorch model REST service and persists scores to the DB.
This task is the middle link in the Celery chain:
    parse_resume_task → score_resume_task → explain_resume_task
"""

import os
import json
import logging
import re
from typing import Dict, Any, Optional

import httpx
import redis
from app.core.database import get_sync_database_url
from celery_app import app
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

AI_MODEL_URL = os.environ.get("AI_MODEL_URL", "http://ai_model:8001")
DB_URL = get_sync_database_url()


def _publish_event(channel: str, payload: Dict[str, Any]) -> None:
    try:
        client = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        client.publish(channel, json.dumps(payload))
        client.close()
    except Exception:
        pass


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9+#.]+", (text or "").lower()) if len(token) > 2}


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_scorer_api(payload: Dict) -> Dict:
    """Call the PyTorch inference REST service with retry."""
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{AI_MODEL_URL}/score", json=payload)
        resp.raise_for_status()
        return resp.json()


def _get_job_details(session, job_id: str) -> Optional[Dict]:
    """Fetch job requirements from DB."""
    from sqlalchemy import text as sql_text
    row = session.execute(
        sql_text("""
            SELECT title, description, requirements, required_skills,
                   preferred_skills, experience_years_min, education_level, created_by_id
            FROM jobs WHERE id = :job_id
        """),
        {"job_id": job_id},
    ).fetchone()
    if not row:
        return None
    return {
        "title": row[0],
        "description": row[1],
        "requirements": row[2],
        "required_skills": row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]"),
        "preferred_skills": row[4] if isinstance(row[4], list) else json.loads(row[4] or "[]"),
        "experience_years_min": row[5] or 0,
        "education_level": row[6] or "",
        "created_by_id": row[7],
    }


def _get_resume_details(session, resume_id: str) -> Optional[Dict]:
    """Fetch parsed resume data from DB."""
    from sqlalchemy import text as sql_text
    row = session.execute(
        sql_text("""
            SELECT raw_text, extracted_skills, years_of_experience, education_level,
                   semantic_summary, candidate_name, candidate_email, candidate_location,
                   certifications, projects, experience_timeline
            FROM resumes WHERE id = :resume_id
        """),
        {"resume_id": resume_id},
    ).fetchone()
    if not row:
        return None
    return {
        "raw_text": row[0] or "",
        "extracted_skills": row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]"),
        "years_of_experience": float(row[2] or 0),
        "education_level": row[3] or "",
        "semantic_summary": row[4] or "",
        "candidate_name": row[5],
        "candidate_email": row[6],
        "candidate_location": row[7],
        "certifications": row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]"),
        "projects": row[9] if isinstance(row[9], list) else json.loads(row[9] or "[]"),
        "experience_timeline": row[10] if isinstance(row[10], list) else json.loads(row[10] or "[]"),
    }


@app.task(
    bind=True,
    name="tasks.ai_scorer.score_resume_task",
    max_retries=3,
    default_retry_delay=30,
    queue="ai_scoring",
    soft_time_limit=180,
    time_limit=240,
)
def score_resume_task(
    self,
    screening_id: str,
    job_id: str,
    resume_id: str,
) -> Dict[str, Any]:
    """
    Score a resume against a job using the PyTorch model service.
    Returns scoring data dict (passed to llm_explainer via chain).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL)
    job = None
    resume = None

    try:
        logger.info(f"Scoring screening={screening_id} job={job_id} resume={resume_id}")

        with Session(engine) as session:
            job = _get_job_details(session, job_id)
            resume = _get_resume_details(session, resume_id)

        if not job:
            raise ValueError(f"Job {job_id} not found")
        if not resume:
            raise ValueError(f"Resume {resume_id} not found")
        if not resume["raw_text"]:
            raise ValueError("Resume has no parsed text — run parser first")

        semantic_score = round(
            100.0 * _jaccard_similarity(
                " ".join([job["title"], job["description"], job["requirements"], " ".join(job["required_skills"]), " ".join(job["preferred_skills"]) ]),
                resume["semantic_summary"] or resume["raw_text"],
            ),
            2,
        )

        # Build scorer payload
        scorer_payload = {
            "resume_text": resume["raw_text"],
            "resume_semantic_summary": resume["semantic_summary"],
            "job_category": job["title"],
            "required_skills": job["required_skills"],
            "preferred_skills": job["preferred_skills"],
            "years_experience_required": job["experience_years_min"],
            "resume_years_experience": resume["years_of_experience"],
            "resume_education_level": resume["education_level"],
            "required_education_level": job["education_level"],
        }

        # Call PyTorch scorer
        score_result = call_scorer_api(scorer_payload)

        # Compute skill sets
        resume_skills_set = set(s.lower() for s in resume["extracted_skills"])
        required_skills_set = set(s.lower() for s in job["required_skills"])
        preferred_skills_set = set(s.lower() for s in job["preferred_skills"])

        matched = sorted(resume_skills_set & required_skills_set)
        missing = sorted(required_skills_set - resume_skills_set)
        bonus = sorted(resume_skills_set & preferred_skills_set - required_skills_set)

        result = {
            "screening_id": screening_id,
            "job_id": job_id,
            "resume_id": resume_id,
            "overall_score": score_result["overall_score"],
            "skill_match_score": score_result["skill_match_score"],
            "experience_score": score_result["experience_score"],
            "education_score": score_result["education_score"],
            "semantic_score": semantic_score,
            "confidence_score": round(min(1.0, 0.45 + semantic_score / 250.0), 3),
            "matched_skills": matched,
            "missing_skills": missing,
            "bonus_skills": bonus,
            # Pass context forward to LLM explainer
            "job_title": job["title"],
            "job_description": job["description"][:1000],
            "resume_text_snippet": resume["raw_text"][:2000],
            "resume_semantic_summary": resume["semantic_summary"],
            "candidate_skills": list(resume["extracted_skills"]),
            "candidate_name": resume["candidate_name"],
            "candidate_email": resume["candidate_email"],
            "candidate_location": resume["candidate_location"],
            "certifications": resume["certifications"],
            "projects": resume["projects"],
            "years_of_experience": resume["years_of_experience"],
            "education_level": resume["education_level"],
        }

        # Persist to DB
        with Session(engine) as session:
            from sqlalchemy import text as sql_text
            session.execute(
                sql_text("""
                    UPDATE screenings SET
                        overall_score = :overall,
                        skill_match_score = :skill,
                        experience_score = :exp,
                        education_score = :edu,
                        semantic_score = :semantic,
                        confidence_score = :confidence,
                        matched_skills = :matched,
                        missing_skills = :missing,
                        bonus_skills = :bonus,
                        score_breakdown = :score_breakdown,
                        status = 'scored',
                        updated_at = NOW()
                    WHERE id = :screening_id
                """),
                {
                    "overall": result["overall_score"],
                    "skill": result["skill_match_score"],
                    "exp": result["experience_score"],
                    "edu": result["education_score"],
                    "semantic": result["semantic_score"],
                    "confidence": result["confidence_score"],
                    "matched": json.dumps(matched),
                    "missing": json.dumps(missing),
                    "bonus": json.dumps(bonus),
                    "score_breakdown": json.dumps({
                        "overall": result["overall_score"],
                        "semantic": result["semantic_score"],
                        "skills": result["skill_match_score"],
                        "experience": result["experience_score"],
                        "education": result["education_score"],
                        "confidence": result["confidence_score"],
                    }),
                    "screening_id": screening_id,
                },
            )
            session.commit()

        logger.info(f"Scored {screening_id}: {result['overall_score']:.1f}/100")
        _publish_event(
            f"screening:{job_id}",
            {
                "type": "screening.scored",
                "screening_id": screening_id,
                "job_id": job_id,
                "resume_id": resume_id,
                "overall_score": result["overall_score"],
                "semantic_score": result["semantic_score"],
                "confidence_score": result["confidence_score"],
            },
        )
        if job.get("created_by_id"):
            _publish_event(
                f"notifications:{job['created_by_id']}",
                {
                    "type": "notification",
                    "title": f"Screening scored for {job['title']}",
                    "message": f"Resume {resume_id} scored {result['overall_score']:.1f}/100",
                    "job_id": job_id,
                    "screening_id": screening_id,
                },
            )
        return result

    except Exception as exc:
        logger.error(f"Scoring failed for {screening_id}: {exc}")
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            from sqlalchemy import text as sql_text
            with Session(create_engine(DB_URL)) as session:
                session.execute(
                    sql_text("UPDATE screenings SET status='failed', error_message=:err, updated_at=NOW() WHERE id=:id"),
                    {"err": str(exc)[:500], "id": screening_id},
                )
                session.commit()
        except Exception:
            pass
        _publish_event(
            f"screening:{job_id}",
            {
                "type": "screening.failed",
                "screening_id": screening_id,
                "job_id": job_id,
                "resume_id": resume_id,
                "error": str(exc)[:500],
            },
        )
        if job and job.get("created_by_id"):
            _publish_event(
                f"notifications:{job['created_by_id']}",
                {
                    "type": "notification",
                    "title": f"Screening failed for {job['title']}",
                    "message": str(exc)[:500],
                    "job_id": job_id,
                    "screening_id": screening_id,
                },
            )
        raise self.retry(exc=exc)
