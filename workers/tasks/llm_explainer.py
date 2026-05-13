"""
HireSense AI — Phase 5: LLM Integration
Celery Task: LLM Explainer using Mistral-7B via Ollama

SDG 8 Alignment:
  - Bias-aware prompt engineering
  - Skills-first evaluation (no demographic inference)
  - Transparent, human-readable explanations
  - Fairness flags for recruiter awareness
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional

import httpx
import redis
from app.core.database import get_sync_database_url
from celery_app import app
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral:7b")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))
DB_URL = get_sync_database_url()


# ── SDG 8 Bias Keywords to Detect ────────────────────────────────────────────
BIAS_INDICATORS = [
    "age", "gender", "race", "ethnicity", "nationality", "religion",
    "marital", "family", "pregnant", "disability", "accent", "photo",
    "young", "old", "female", "male", "he ", "she ", "his ", "her ",
]


def check_for_bias(text: str) -> List[str]:
    """Detect potential bias indicators in LLM output. SDG 8 fairness check."""
    flags = []
    text_lower = text.lower()
    for indicator in BIAS_INDICATORS:
        if indicator in text_lower:
            flags.append(indicator.strip())
    return list(set(flags))


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


def _retrieve_context(resume_id: str, resume_summary: str) -> List[Dict[str, Any]]:
    from sqlalchemy import create_engine, text as sql_text
    from sqlalchemy.orm import Session

    engine = create_engine(DB_URL)
    context: List[Dict[str, Any]] = []
    with Session(engine) as session:
        rows = session.execute(
            sql_text("""
                SELECT id, candidate_name, semantic_summary, extracted_skills, years_of_experience
                FROM resumes
                WHERE id != :resume_id
            """),
            {"resume_id": resume_id},
        ).fetchall()
        for row in rows:
            summary = row[2] or ""
            similarity = _jaccard_similarity(resume_summary, summary)
            context.append(
                {
                    "type": "similar_candidate",
                    "resume_id": str(row[0]),
                    "candidate_name": row[1],
                    "similarity": round(similarity * 100.0, 2),
                    "skills": row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]"),
                    "years_of_experience": float(row[4] or 0),
                }
            )
    context.sort(key=lambda item: item["similarity"], reverse=True)
    return context[:4]


# ── Prompt Templates ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are HireSense AI, an impartial and ethical AI hiring assistant aligned with 
UN Sustainable Development Goal 8 (Decent Work and Economic Growth).

CORE PRINCIPLES:
1. Evaluate candidates ONLY on skills, experience, education, and relevant achievements.
2. NEVER reference or infer age, gender, race, nationality, religion, or any protected characteristic.
3. Be constructive, specific, and evidence-based in your analysis.
4. Flag any concerns about skills gaps as development opportunities, not disqualifiers.
5. Promote fair access to economic opportunities for all candidates.

OUTPUT FORMAT: Always respond in valid JSON only. No markdown, no preamble."""


def build_explanation_prompt(data: Dict, retrieved_context: List[Dict[str, Any]]) -> str:
    context_lines = []
    for item in retrieved_context[:4]:
        context_lines.append(
            f"- {item.get('candidate_name') or item.get('resume_id')} | similarity={item.get('similarity')} | "
            f"skills={', '.join(item.get('skills', [])[:8])} | exp={item.get('years_of_experience')}"
        )
    context_block = "\n".join(context_lines) if context_lines else "- No additional retrieval context"

    return f"""Analyze this resume-job match and provide a structured JSON explanation.

JOB DETAILS:
- Title: {data['job_title']}
- Description: {data['job_description']}

CANDIDATE PROFILE:
- Years of Experience: {data['years_of_experience']}
- Education: {data['education_level']}
- Identified Skills: {', '.join(data['candidate_skills'][:20])}

SCORING SUMMARY:
- Overall Match Score: {data['overall_score']}/100
- Skill Match: {data['skill_match_score']}/100
- Experience: {data['experience_score']}/100
- Education: {data['education_score']}/100
- Semantic Match: {data.get('semantic_score', 0)}/100
- Confidence: {data.get('confidence_score', 0)}
- Matched Skills: {', '.join(data['matched_skills'][:15])}
- Missing Skills: {', '.join(data['missing_skills'][:10])}
- Bonus Skills: {', '.join(data['bonus_skills'][:10])}

Resume Excerpt:
\"\"\"
{data['resume_text_snippet'][:1500]}
\"\"\"

Retrieved Context:
{context_block}

Provide a JSON response with EXACTLY this structure:
{{
  "recommendation": "strong_yes" | "yes" | "maybe" | "no",
  "explanation": "2-3 paragraph professional explanation of the match quality, focusing on skills and experience",
  "strengths": ["specific strength 1", "specific strength 2", "specific strength 3"],
  "concerns": ["specific concern or gap 1", "specific concern 2"],
  "development_opportunities": ["skill to develop 1", "skill to develop 2"],
  "interview_questions": ["suggested question 1", "suggested question 2", "suggested question 3"],
  "sdg8_note": "Brief note on how hiring this candidate supports decent work"
}}"""


def build_recommendation(score: float) -> str:
    if score >= 80:
        return "strong_yes"
    elif score >= 65:
        return "yes"
    elif score >= 45:
        return "maybe"
    return "no"


# ── Ollama Client ─────────────────────────────────────────────────────────────
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
def call_ollama(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Call Ollama REST API with Mistral-7B."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_predict": LLM_MAX_TOKENS,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        resp = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def parse_llm_response(raw: str) -> Dict:
    """Safely parse JSON from LLM output, handling markdown fences."""
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback structure
    return {
        "recommendation": "maybe",
        "explanation": raw[:1000] if raw else "Unable to generate explanation.",
        "strengths": [],
        "concerns": [],
        "development_opportunities": [],
        "interview_questions": [],
        "sdg8_note": "Evaluation based on skills and experience only.",
    }


def is_ollama_available() -> bool:
    """Check if Ollama service is reachable."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def generate_fallback_explanation(data: Dict) -> Dict:
    """
    Rule-based fallback explanation when LLM is unavailable.
    Ensures system remains functional without Ollama.
    """
    score = data["overall_score"]
    matched = data["matched_skills"]
    missing = data["missing_skills"]
    recommendation = build_recommendation(score)

    if score >= 80:
        quality = "excellent"
        outlook = "This candidate demonstrates strong alignment with the role requirements."
    elif score >= 65:
        quality = "good"
        outlook = "This candidate shows solid potential with most key requirements met."
    elif score >= 45:
        quality = "moderate"
        outlook = "This candidate meets some requirements but has notable gaps."
    else:
        quality = "limited"
        outlook = "This candidate does not currently meet the core requirements."

    matched_str = ", ".join(matched[:5]) if matched else "few required skills"
    missing_str = ", ".join(missing[:5]) if missing else "none critical"

    explanation = (
        f"This candidate achieved an overall match score of {score:.1f}/100, "
        f"indicating a {quality} fit for the {data['job_title']} role. "
        f"{outlook}\n\n"
        f"Key matched skills include: {matched_str}. "
        f"Areas requiring development: {missing_str}. "
        f"With {data['years_of_experience']} years of experience and a {data['education_level']} "
        f"background, the candidate's profile has been evaluated purely on merit and competency."
    )

    return {
        "recommendation": recommendation,
        "explanation": explanation,
        "strengths": [f"Demonstrates: {s}" for s in matched[:3]],
        "concerns": [f"Missing skill: {s}" for s in missing[:3]],
        "development_opportunities": missing[:3],
        "interview_questions": [
            f"Can you describe your experience with {matched[0]}?" if matched else "Tell us about your technical background.",
            "What is your approach to learning new technologies?",
            "Describe a challenging project and how you overcame obstacles.",
        ],
        "sdg8_note": "Candidate evaluated on skills and experience in support of fair, merit-based hiring (SDG 8).",
    }


# ── Main Celery Task ──────────────────────────────────────────────────────────
@app.task(
    bind=True,
    name="tasks.llm_explainer.explain_resume_task",
    max_retries=2,
    default_retry_delay=60,
    queue="llm_explain",
    soft_time_limit=180,
    time_limit=240,
)
def explain_resume_task(self, score_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate LLM-powered explanation for a resume-job screening result.
    Uses Mistral-7B via Ollama. Falls back to rule-based explanation if unavailable.
    Final task in the pipeline chain.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy import text as sql_text

    screening_id = score_data.get("screening_id")
    job_id = score_data.get("job_id")
    job_owner = None
    logger.info(f"Generating LLM explanation for screening={screening_id}")

    try:
        retrieved_context = _retrieve_context(
            str(score_data.get("resume_id")),
            score_data.get("resume_semantic_summary") or score_data.get("resume_text_snippet", ""),
        )
        # 1. Try LLM explanation
        if is_ollama_available():
            prompt = build_explanation_prompt(score_data, retrieved_context)
            raw_response = call_ollama(prompt)
            llm_result = parse_llm_response(raw_response)
            logger.info(f"LLM explanation generated for {screening_id}")
        else:
            logger.warning("Ollama unavailable — using rule-based fallback")
            llm_result = generate_fallback_explanation(score_data)

        # 2. SDG 8 Bias check on LLM output
        explanation_text = llm_result.get("explanation", "")
        bias_flags = check_for_bias(explanation_text)
        bias_detected = len(bias_flags) > 0

        if bias_detected:
            logger.warning(f"Bias indicators detected in explanation: {bias_flags}")
            # Sanitize: replace with fallback if bias found
            llm_result = generate_fallback_explanation(score_data)
            bias_flags = ["content_sanitized_for_fairness"]

        llm_result.setdefault("development_opportunities", score_data.get("missing_skills", [])[:3])
        llm_result.setdefault("interview_questions", [])
        llm_result.setdefault("sdg8_note", "Candidate evaluated on skills, experience, and education only.")
        llm_result["bias_keywords"] = bias_flags
        llm_result["retrieved_context"] = retrieved_context

        # 3. Persist to DB
        engine = create_engine(DB_URL)
        with Session(engine) as session:
            job_owner = session.execute(
                sql_text("SELECT created_by_id FROM jobs WHERE id = :job_id"),
                {"job_id": job_id},
            ).scalar_one_or_none()
            session.execute(
                sql_text("""
                    UPDATE screenings SET
                        ai_explanation = :explanation,
                        ai_recommendation = :recommendation,
                        ai_strengths = :strengths,
                        ai_concerns = :concerns,
                        retrieved_context = :retrieved_context,
                        explanation_context = :explanation_context,
                        llm_model = :llm_model,
                        fairness_flags = :flags,
                        bias_keywords = :bias_keywords,
                        bias_detected = :bias,
                        fairness_score = :fairness_score,
                        status = 'explained',
                        updated_at = NOW()
                    WHERE id = :screening_id
                """),
                {
                    "explanation": llm_result.get("explanation", "")[:5000],
                    "recommendation": llm_result.get("recommendation", "maybe"),
                    "strengths": json.dumps(llm_result.get("strengths", [])),
                    "concerns": json.dumps(llm_result.get("concerns", [])),
                    "flags": json.dumps(bias_flags),
                    "bias_keywords": json.dumps(bias_flags),
                    "bias": bias_detected,
                    "retrieved_context": json.dumps(retrieved_context),
                    "explanation_context": json.dumps(
                        {
                            "job_title": score_data.get("job_title"),
                            "job_description": score_data.get("job_description"),
                            "semantic_score": score_data.get("semantic_score"),
                            "confidence_score": score_data.get("confidence_score"),
                            "retrieved_context": retrieved_context,
                            "development_opportunities": llm_result.get("development_opportunities", []),
                            "interview_questions": llm_result.get("interview_questions", []),
                        }
                    ),
                    "llm_model": LLM_MODEL,
                    "fairness_score": max(0.0, 100.0 - (len(bias_flags) * 12.5)),
                    "screening_id": screening_id,
                },
            )
            session.commit()

        logger.info(
            f"Explanation saved for {screening_id} | "
            f"recommendation={llm_result.get('recommendation')} | "
            f"bias_detected={bias_detected}"
        )
        if job_id:
            _publish_event(
                f"screening:{job_id}",
                {
                    "type": "screening.explained",
                    "screening_id": screening_id,
                    "job_id": job_id,
                    "recommendation": llm_result.get("recommendation"),
                    "bias_detected": bias_detected,
                    "llm_model": LLM_MODEL,
                },
            )
        if job_id and job_owner:
            _publish_event(
                f"notifications:{job_owner}",
                {
                    "type": "notification",
                    "title": f"Explanation ready for screening {screening_id}",
                    "message": f"LLM explanation completed with recommendation {llm_result.get('recommendation')}",
                    "job_id": job_id,
                    "screening_id": screening_id,
                },
            )

        return {
            "screening_id": screening_id,
            "status": "explained",
            "recommendation": llm_result.get("recommendation"),
            "bias_detected": bias_detected,
            "bias_keywords": bias_flags,
            "retrieved_context": retrieved_context,
            "llm_model": LLM_MODEL,
        }

    except Exception as exc:
        logger.error(f"LLM explanation failed for {screening_id}: {exc}")
        # Store fallback even on error so UI isn't stuck
        try:
            fallback = generate_fallback_explanation(score_data)
            engine = create_engine(DB_URL)
            with Session(engine) as session:
                from sqlalchemy import text as sql_text
                job_owner = session.execute(
                    sql_text("SELECT created_by_id FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).scalar_one_or_none()
                session.execute(
                    sql_text("""
                        UPDATE screenings SET
                            ai_explanation = :explanation,
                            ai_recommendation = :recommendation,
                            ai_strengths = :strengths,
                            ai_concerns = :concerns,
                            fairness_flags = :fairness_flags,
                            bias_keywords = :bias_keywords,
                            bias_detected = :bias,
                            fairness_score = :fairness_score,
                            retrieved_context = :retrieved_context,
                            explanation_context = :explanation_context,
                            llm_model = :llm_model,
                            status = 'explained',
                            error_message = :err,
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "explanation": fallback["explanation"],
                        "recommendation": fallback["recommendation"],
                        "strengths": json.dumps(fallback.get("strengths", [])),
                        "concerns": json.dumps(fallback.get("concerns", [])),
                        "fairness_flags": json.dumps([]),
                        "bias_keywords": json.dumps([]),
                        "bias": False,
                        "fairness_score": 100.0,
                        "retrieved_context": json.dumps([]),
                        "explanation_context": json.dumps({}),
                        "llm_model": LLM_MODEL,
                        "err": str(exc)[:500],
                        "id": screening_id,
                    },
                )
                session.commit()
        except Exception:
            pass
        if job_id:
            _publish_event(
                f"screening:{job_id}",
                {
                    "type": "screening.explained",
                    "screening_id": screening_id,
                    "job_id": job_id,
                    "recommendation": fallback["recommendation"],
                    "bias_detected": False,
                },
            )
        if job_id and job_owner:
            _publish_event(
                f"notifications:{job_owner}",
                {
                    "type": "notification",
                    "title": f"Explanation fallback for screening {screening_id}",
                    "message": f"Fallback explanation stored after error: {str(exc)[:120]}",
                    "job_id": job_id,
                    "screening_id": screening_id,
                },
            )
        raise self.retry(exc=exc)
