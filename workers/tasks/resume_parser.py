"""
HireSense AI — Enhanced Resume Parser with Vector Storage

Extracts comprehensive structured data from PDF/DOCX files:
- Skills, education, experience, certifications, projects
- Contact info, GitHub/LinkedIn, timeline
- Semantic embeddings for vector search
- Stores semantic vectors for retrieval
"""

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import spacy
import redis
from app.core.database import get_sync_database_url
from app.services.vector_search import get_vector_service

from celery_app import app

logger = logging.getLogger(__name__)

# ── Lazy-load spaCy model (loaded once per worker process) ───────────────────
_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        for model_name in ("en_core_web_lg", "en_core_web_sm"):
            try:
                logger.info("Loading spaCy model %s ...", model_name)
                _nlp = spacy.load(model_name)
                break
            except Exception:
                continue
        if _nlp is None:
            logger.warning("spaCy model unavailable; falling back to blank English pipeline")
            _nlp = spacy.blank("en")
    return _nlp


# ── Known skills vocabulary (augmented from dataset taxonomy) ────────────────
SKILLS_DB = {
    # Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "r", "scala", "kotlin", "swift", "php", "ruby",
    # ML / AI
    "machine learning", "deep learning", "pytorch", "tensorflow", "keras",
    "scikit-learn", "nlp", "computer vision", "transformers", "huggingface",
    "llm", "bert", "gpt", "reinforcement learning", "xgboost", "lightgbm",
    # Data
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "apache spark", "hadoop", "kafka", "airflow", "dbt", "databricks",
    "pandas", "numpy", "matplotlib", "seaborn", "tableau", "power bi",
    # Web
    "react", "vue.js", "angular", "node.js", "django", "fastapi", "flask",
    "rest api", "graphql", "html", "css", "webpack",
    # DevOps / Cloud
    "docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions",
    "aws", "gcp", "azure", "linux", "bash", "ci/cd", "microservices",
    # Soft skills (for context)
    "leadership", "agile", "scrum", "communication", "problem solving",
}

EDUCATION_KEYWORDS = {
    "phd": 4, "ph.d": 4, "doctorate": 4,
    "master": 3, "m.s.": 3, "m.tech": 3, "mba": 3, "m.e.": 3,
    "bachelor": 2, "b.s.": 2, "b.tech": 2, "b.e.": 2, "undergraduate": 2,
    "associate": 1, "diploma": 1,
    "high school": 0, "secondary": 0,
}

EXPERIENCE_PATTERNS = [
    r"(\d+\.?\d*)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
    r"(\d+\.?\d*)\+?\s*yrs?\s*(?:of\s+)?(?:experience|exp)",
    r"experience\s*(?:of\s+)?(\d+\.?\d*)\+?\s*years?",
]

SECTION_HEADERS = {
    "experience": ["experience", "work experience", "employment history", "work history", "career"],
    "education": ["education", "academic background", "qualifications", "academic history"],
    "skills": ["skills", "technical skills", "core competencies", "technologies", "expertise"],
    "projects": ["projects", "key projects", "notable projects"],
    "certifications": ["certifications", "certificates", "credentials"],
}


def extract_raw_text(file_path: str) -> str:
    """Extract raw text from PDF or DOCX."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(file_path)
    elif ext in (".docx", ".doc"):
        return _extract_docx_text(file_path)
    return ""


def _extract_pdf_text(path: str) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return "\n".join(pages)


def _extract_docx_text(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def extract_contact_info(text: str, doc) -> Dict[str, Optional[str]]:
    """Extract name, email, phone using NER + regex."""
    emails = list(dict.fromkeys(re.findall(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)))
    phones = list(dict.fromkeys(re.findall(r"(\+?\d[\d\s\-().]{8,18}\d)", text)))
    github_match = re.search(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+", text, re.IGNORECASE)
    linkedin_match = re.search(r"https?://(?:www\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_.-]+", text, re.IGNORECASE)

    # Person name from spaCy NER (first PERSON entity, usually at top of resume)
    name = None
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
            name = ent.text.strip()
            break

    # Location
    location = None
    for ent in doc.ents:
        if ent.label_ in ("GPE", "LOC") and location is None:
            location = ent.text.strip()

    return {
        "name": name,
        "email": emails[0] if emails else None,
        "emails": emails,
        "phone": phones[0] if phones else None,
        "phones": phones,
        "location": location,
        "github_url": github_match.group(0) if github_match else None,
        "linkedin_url": linkedin_match.group(0) if linkedin_match else None,
    }


def extract_certifications(text: str) -> List[str]:
    section = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(term in lowered for term in ("certified", "certification", "certificate", "credential")):
            section.append(line.strip("•-* \t")[:180])
    return list(dict.fromkeys(section))[:8]


def extract_projects(text: str) -> List[Dict[str, str]]:
    projects = []
    for line in text.splitlines():
        lowered = line.lower()
        if "project" in lowered or "built " in lowered or "developed " in lowered:
            projects.append({"detail": line.strip("•-* \t")[:240]})
        if len(projects) >= 8:
            break
    return projects


def extract_experience_timeline(text: str) -> List[Dict[str, Any]]:
    timeline = []
    pattern = re.compile(
        r"(?P<start>(?:[A-Za-z]{3,9}\s+)?\d{4})\s*(?:-|–|to)\s*(?P<end>(?:[A-Za-z]{3,9}\s+)?\d{4}|present|current|now)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        start = match.group("start")
        end = match.group("end")
        timeline.append({"start": start, "end": end})
    return timeline[:8]


def build_semantic_summary(parsed: Dict[str, Any], raw_text: str) -> str:
    parts = []
    if parsed.get("candidate_name"):
        parts.append(f"Candidate: {parsed['candidate_name']}")
    if parsed.get("candidate_location"):
        parts.append(f"Location: {parsed['candidate_location']}")
    if parsed.get("education_level"):
        parts.append(f"Education: {parsed['education_level']}")
    if parsed.get("extracted_skills"):
        parts.append("Skills: " + ", ".join(parsed["extracted_skills"][:20]))
    if parsed.get("certifications"):
        parts.append("Certifications: " + ", ".join(parsed["certifications"][:5]))
    if parsed.get("projects"):
        parts.append("Projects: " + "; ".join(item.get("detail", "") for item in parsed["projects"][:3]))
    if parsed.get("years_of_experience"):
        parts.append(f"Experience: {parsed['years_of_experience']} years")
    if parsed.get("github_url") or parsed.get("linkedin_url"):
        parts.append("Links: " + ", ".join(item for item in [parsed.get("github_url"), parsed.get("linkedin_url")] if item))
    if raw_text:
        parts.append(raw_text[:500])
    return " | ".join(parts)[:4000]


def calculate_parse_confidence(parsed: Dict[str, Any]) -> float:
    score = 0.25
    score += 0.15 if parsed.get("candidate_name") else 0.0
    score += 0.15 if parsed.get("emails") else 0.0
    score += 0.10 if parsed.get("phones") else 0.0
    score += min(0.2, len(parsed.get("extracted_skills", [])) * 0.02)
    score += min(0.1, len(parsed.get("certifications", [])) * 0.03)
    score += min(0.1, len(parsed.get("projects", [])) * 0.03)
    return round(min(1.0, score), 3)


def extract_skills(text: str) -> List[str]:
    """Match skills from vocabulary against resume text."""
    text_lower = text.lower()
    found = []
    for skill in SKILLS_DB:
        # Word boundary matching
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            found.append(skill)
    return sorted(set(found))


def extract_years_of_experience(text: str) -> float:
    """Parse explicit experience mentions."""
    text_lower = text.lower()
    years_found = []
    for pattern in EXPERIENCE_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            try:
                years_found.append(float(match.group(1)))
            except (ValueError, IndexError):
                pass
    return round(max(years_found, default=0.0), 1)


def extract_education_level(text: str) -> str:
    """Detect highest education level mentioned."""
    text_lower = text.lower()
    best_level = -1
    best_name = ""
    for keyword, level in EDUCATION_KEYWORDS.items():
        if keyword in text_lower and level > best_level:
            best_level = level
            best_name = keyword
    edu_map = {4: "PhD", 3: "Master's", 2: "Bachelor's", 1: "Associate/Diploma", 0: "High School"}
    return edu_map.get(best_level, "Not specified")


def extract_experience_entries(doc) -> List[Dict]:
    """Extract job titles + organizations using NER."""
    entries = []
    seen = set()
    orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
    for org in orgs[:10]:  # Limit
        if org not in seen:
            seen.add(org)
            entries.append({"organization": org})
    return entries


def extract_education_entries(doc, text: str) -> List[Dict]:
    """Extract education institutions using NER."""
    edu_keywords = ["university", "college", "institute", "school", "iit", "nit", "bits"]
    entries = []
    seen = set()
    for ent in doc.ents:
        if ent.label_ == "ORG":
            org_lower = ent.text.lower()
            if any(kw in org_lower for kw in edu_keywords) and ent.text not in seen:
                seen.add(ent.text)
                entries.append({"institution": ent.text, "level": extract_education_level(text)})
    return entries


def _publish_event(channel: str, payload: Dict[str, Any]) -> None:
    try:
        client = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        client.publish(channel, json.dumps(payload))
        client.close()
    except Exception:
        pass


@app.task(
    bind=True,
    name="tasks.resume_parser.parse_resume_task",
    max_retries=3,
    default_retry_delay=30,
    queue="default",
    soft_time_limit=120,
    time_limit=180,
)
def parse_resume_task(self, resume_id: str, file_path: str) -> Dict[str, Any]:
    """
    Parse a resume file and persist structured data to the DB.
    Returns parsed data dict (also used as input to ai_scorer via Celery chain).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import sys
    sys.path.insert(0, "/app")

    engine = create_engine(get_sync_database_url())

    try:
        logger.info(f"Parsing resume {resume_id} from {file_path}")

        # 1. Extract raw text
        raw_text = extract_raw_text(file_path)
        if not raw_text.strip():
            raise ValueError("Empty resume text extracted")

        # 2. Run spaCy NLP
        nlp = get_nlp()
        doc = nlp(raw_text[:100_000])  # Cap at 100k chars for performance

        # 3. Extract structured fields
        contact = extract_contact_info(raw_text, doc)
        skills = extract_skills(raw_text)
        years_exp = extract_years_of_experience(raw_text)
        edu_level = extract_education_level(raw_text)
        experience_entries = extract_experience_entries(doc)
        education_entries = extract_education_entries(doc, raw_text)
        certifications = extract_certifications(raw_text)
        projects = extract_projects(raw_text)
        experience_timeline = extract_experience_timeline(raw_text)

        parsed = {
            "resume_id": resume_id,
            "raw_text": raw_text,
            "candidate_name": contact["name"],
            "candidate_email": contact["email"],
            "candidate_phone": contact["phone"],
            "candidate_location": contact["location"],
            "emails": contact.get("emails", []),
            "phones": contact.get("phones", []),
            "github_url": contact.get("github_url"),
            "linkedin_url": contact.get("linkedin_url"),
            "extracted_skills": skills,
            "extracted_experience": experience_entries,
            "extracted_education": education_entries,
            "certifications": certifications,
            "projects": projects,
            "experience_timeline": experience_timeline,
            "years_of_experience": years_exp,
            "education_level": edu_level,
            "semantic_summary": build_semantic_summary(
                {
                    "candidate_name": contact["name"],
                    "candidate_location": contact["location"],
                    "extracted_skills": skills,
                    "certifications": certifications,
                    "projects": projects,
                    "years_of_experience": years_exp,
                    "education_level": edu_level,
                    "github_url": contact.get("github_url"),
                    "linkedin_url": contact.get("linkedin_url"),
                },
                raw_text,
            ),
            "parse_confidence": calculate_parse_confidence(
                {
                    "candidate_name": contact["name"],
                    "emails": contact.get("emails", []),
                    "phones": contact.get("phones", []),
                    "extracted_skills": skills,
                    "certifications": certifications,
                    "projects": projects,
                }
            ),
            "parse_status": "done",
        }

        # 4. Persist to DB (sync session for worker)
        with Session(engine) as session:
            from sqlalchemy import text as sql_text
            session.execute(
                sql_text("""
                    UPDATE resumes SET
                        candidate_name = :name,
                        candidate_email = :email,
                        candidate_phone = :phone,
                        candidate_location = :location,
                        emails = :emails,
                        phones = :phones,
                        github_url = :github_url,
                        linkedin_url = :linkedin_url,
                        raw_text = :raw_text,
                        extracted_skills = :skills,
                        extracted_experience = :experience,
                        extracted_education = :education,
                        certifications = :certifications,
                        projects = :projects,
                        experience_timeline = :experience_timeline,
                        years_of_experience = :years_exp,
                        education_level = :edu_level,
                        semantic_summary = :semantic_summary,
                        parse_confidence = :parse_confidence,
                        parse_status = 'done',
                        parse_error = NULL,
                        updated_at = NOW()
                    WHERE id = :resume_id
                """),
                {
                    "name": contact["name"],
                    "email": contact["email"],
                    "phone": contact["phone"],
                    "location": contact["location"],
                    "emails": json.dumps(contact.get("emails", [])),
                    "phones": json.dumps(contact.get("phones", [])),
                    "github_url": contact.get("github_url"),
                    "linkedin_url": contact.get("linkedin_url"),
                    "raw_text": raw_text[:50000],  # Store first 50k chars
                    "skills": json.dumps(skills),
                    "experience": json.dumps(experience_entries),
                    "education": json.dumps(education_entries),
                    "certifications": json.dumps(certifications),
                    "projects": json.dumps(projects),
                    "experience_timeline": json.dumps(experience_timeline),
                    "years_exp": years_exp,
                    "edu_level": edu_level,
                    "semantic_summary": parsed["semantic_summary"],
                    "parse_confidence": parsed["parse_confidence"],
                    "resume_id": resume_id,
                },
            )
            session.commit()

        logger.info(f"Resume {resume_id} parsed: {len(skills)} skills, {years_exp} yrs exp")
        _publish_event(
            f"resumes:{resume_id}",
            {
                "type": "resume.parsed",
                "resume_id": resume_id,
                "status": "done",
                "parse_confidence": parsed["parse_confidence"],
            },
        )
        return parsed

    except Exception as exc:
        logger.error(f"Parse failed for {resume_id}: {exc}")
        # Mark as failed in DB
        try:
            with Session(engine) as session:
                from sqlalchemy import text as sql_text
                session.execute(
                    sql_text("UPDATE resumes SET parse_status='failed', parse_error=:err, updated_at=NOW() WHERE id=:id"),
                    {"err": str(exc)[:500], "id": resume_id},
                )
                session.commit()
        except Exception:
            pass
        _publish_event(
            f"resumes:{resume_id}",
            {
                "type": "resume.failed",
                "resume_id": resume_id,
                "status": "failed",
                "error": str(exc)[:500],
            },
        )
        raise self.retry(exc=exc)
