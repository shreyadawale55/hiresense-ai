"""Resume parsing utilities with regex, optional spaCy, and document extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:  # Optional dependency in some environments
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional import
    fitz = None

try:  # Optional dependency in some environments
    from docx import Document
except Exception:  # pragma: no cover - optional import
    Document = None

try:  # Optional spaCy model
    import spacy
except Exception:  # pragma: no cover - optional import
    spacy = None


SKILL_VOCABULARY = sorted(
    {
        "python",
        "pytorch",
        "tensorflow",
        "scikit-learn",
        "fastapi",
        "django",
        "flask",
        "react",
        "node.js",
        "typescript",
        "javascript",
        "sql",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "celery",
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "terraform",
        "linux",
        "bash",
        "git",
        "github actions",
        "microservices",
        "rest api",
        "graphql",
        "nlp",
        "computer vision",
        "machine learning",
        "deep learning",
        "llm",
        "rag",
        "vector database",
        "faiss",
        "chroma",
        "sentence-transformers",
        "transformers",
        "spacy",
        "streamlit",
        "data science",
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "airflow",
        "spark",
        "hadoop",
        "mlops",
        "fairness",
        "bias detection",
        "prompt engineering",
    },
    key=len,
    reverse=True,
)

EDUCATION_LEVELS = {
    "phd": 4,
    "doctorate": 4,
    "master": 3,
    "m.tech": 3,
    "mba": 3,
    "bachelor": 2,
    "b.tech": 2,
    "b.e.": 2,
    "associate": 1,
    "diploma": 1,
    "high school": 0,
}

EDUCATION_LABELS = {
    4: "PhD",
    3: "Master's",
    2: "Bachelor's",
    1: "Associate/Diploma",
    0: "High School",
}

SECTION_HEADERS = {
    "experience": ["experience", "work experience", "employment history", "career history"],
    "education": ["education", "academic background", "qualifications", "academic history"],
    "skills": ["skills", "technical skills", "core competencies", "technologies", "expertise"],
    "projects": ["projects", "project experience", "selected projects", "key projects"],
    "certifications": ["certifications", "certificates", "credentials"],
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp
    if spacy is None:
        return None
    for model_name in ("en_core_web_sm", "en_core_web_lg"):
        try:
            _nlp = spacy.load(model_name)
            return _nlp
        except Exception:
            continue
    try:
        _nlp = spacy.blank("en")
    except Exception:
        _nlp = None
    return _nlp


def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF, DOCX, or plain text files."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf" and fitz is not None:
        doc = fitz.open(file_path)
        try:
            return "\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()

    if suffix in {".docx", ".doc"} and Document is not None:
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    try:
        return Path(file_path).read_text(errors="ignore")
    except Exception:
        return ""


def _find_all(pattern: str, text: str, flags: int = re.IGNORECASE) -> list[str]:
    return [match.group(0) for match in re.finditer(pattern, text, flags)]


def _extract_candidate_name(text: str) -> str | None:
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text[:8000])
        for ent in getattr(doc, "ents", []):
            if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
                return ent.text.strip()

    for line in text.splitlines()[:15]:
        candidate = line.strip()
        if not candidate or "@" in candidate or len(candidate) > 60:
            continue
        words = candidate.split()
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words):
            return candidate
    return None


def _extract_email_list(text: str) -> list[str]:
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    seen: set[str] = set()
    ordered: list[str] = []
    for email in emails:
        normalized = email.strip().lower()
        if normalized not in seen:
            ordered.append(email.strip())
            seen.add(normalized)
    return ordered


def _extract_phone_list(text: str) -> list[str]:
    phones = re.findall(r"(\+?\d[\d\s\-().]{8,18}\d)", text)
    seen: set[str] = set()
    ordered: list[str] = []
    for phone in phones:
        normalized = re.sub(r"\s+", " ", phone).strip()
        if normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered


def _extract_github(text: str) -> str | None:
    match = re.search(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+", text, re.IGNORECASE)
    return match.group(0) if match else None


def _extract_linkedin(text: str) -> str | None:
    match = re.search(
        r"https?://(?:www\.)?linkedin\.com/(?:in|pub)/[A-Za-z0-9_.-]+",
        text,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


def _extract_location(text: str) -> str | None:
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text[:8000])
        for ent in getattr(doc, "ents", []):
            if ent.label_ in {"GPE", "LOC"}:
                return ent.text.strip()

    for line in text.splitlines()[:20]:
        candidate = line.strip()
        if not candidate or "@" in candidate or len(candidate) > 80:
            continue
        if re.search(r"\b[A-Za-z .'-]+,\s*[A-Za-z .'-]{2,}\b", candidate) and not any(
            ch.isdigit() for ch in candidate
        ):
            return candidate
    return None


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for skill in SKILL_VOCABULARY:
        if re.search(r"\b" + re.escape(skill) + r"\b", lowered):
            found.append(skill)
    return found


def extract_years_of_experience(text: str) -> float:
    lowered = text.lower()
    years_found: list[float] = []
    for pattern in (
        r"(\d+\.?\d*)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
        r"(\d+\.?\d*)\+?\s*yrs?\s*(?:of\s+)?(?:experience|exp)",
        r"experience\s*(?:of\s+)?(\d+\.?\d*)\+?\s*years?",
    ):
        for match in re.finditer(pattern, lowered):
            try:
                years_found.append(float(match.group(1)))
            except (ValueError, IndexError):
                continue

    # Heuristic for date ranges like 2020-2023 or Jan 2021 - Present
    for start, end in _extract_date_ranges(text):
        if start and end:
            delta_years = max(0.0, (end - start).days / 365.25)
            if delta_years:
                years_found.append(delta_years)
    return round(max(years_found, default=0.0), 1)


def _month_from_string(value: str) -> int | None:
    return MONTHS.get(value.strip().lower()[:3]) or MONTHS.get(value.strip().lower())


def _parse_date_token(token: str) -> datetime | None:
    token = token.strip()
    if not token or token.lower() in {"present", "current", "now"}:
        return datetime.utcnow()

    match = re.match(r"(?:(?P<month>[A-Za-z]{3,9})[\s.,-]+)?(?P<year>\d{4})", token)
    if match:
        year = int(match.group("year"))
        month = _month_from_string(match.group("month") or "jan") or 1
        return datetime(year, month, 1)

    if re.fullmatch(r"\d{4}", token):
        return datetime(int(token), 1, 1)
    return None


def _extract_date_ranges(text: str) -> list[tuple[datetime | None, datetime | None]]:
    ranges: list[tuple[datetime | None, datetime | None]] = []
    patterns = [
        r"(?P<start>(?:[A-Za-z]{3,9}\s+)?\d{4})\s*(?:-|–|to)\s*(?P<end>(?:[A-Za-z]{3,9}\s+)?\d{4}|present|current|now)",
        r"(?P<start>\d{4})\s*(?:-|–|to)\s*(?P<end>\d{4}|present|current|now)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = _parse_date_token(match.group("start"))
            end = _parse_date_token(match.group("end"))
            ranges.append((start, end))
    return ranges


def _infer_section_lines(text: str, section_names: Iterable[str]) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lowered = [line.lower() for line in lines]
    for idx, line in enumerate(lowered):
        if any(header in line for header in section_names):
            collected: list[str] = []
            for candidate in lines[idx + 1 : idx + 12]:
                if re.match(r"^[A-Z][A-Z\s]{3,}$", candidate):
                    break
                if any(header in candidate.lower() for header in SECTION_HEADERS["skills"] + SECTION_HEADERS["experience"] + SECTION_HEADERS["education"]):
                    break
                collected.append(candidate)
            return collected
    return []


def extract_education_level(text: str) -> str:
    lowered = text.lower()
    best_level = -1
    for keyword, level in EDUCATION_LEVELS.items():
        if keyword in lowered and level > best_level:
            best_level = level
    return EDUCATION_LABELS.get(best_level, "Not specified")


def extract_education_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    section_lines = _infer_section_lines(text, SECTION_HEADERS["education"])
    for line in section_lines[:8]:
        entries.append({"detail": line[:240]})
    if entries:
        return entries

    for line in text.splitlines():
        lowered = line.lower()
        if any(keyword in lowered for keyword in ("university", "college", "institute", "degree", "school")):
            entries.append({"detail": line.strip()[:240]})
        if len(entries) >= 5:
            break
    return entries


def extract_certifications(text: str) -> list[str]:
    entries: list[str] = []
    section_lines = _infer_section_lines(text, SECTION_HEADERS["certifications"])
    for line in section_lines:
        cleaned = line.strip("•-* \t")
        if cleaned:
            entries.append(cleaned[:180])
    if entries:
        return entries

    for line in text.splitlines():
        lowered = line.lower()
        if any(term in lowered for term in ("certified", "certification", "certificate", "credential")):
            entries.append(line.strip()[:180])
        if len(entries) >= 5:
            break
    return entries


def extract_projects(text: str) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    section_lines = _infer_section_lines(text, SECTION_HEADERS["projects"])
    if section_lines:
        for line in section_lines[:8]:
            cleaned = line.strip("•-* \t")
            if cleaned:
                projects.append({"detail": cleaned[:240]})
        return projects

    for line in text.splitlines():
        lowered = line.lower()
        if "project" in lowered or "built " in lowered or "developed " in lowered:
            projects.append({"detail": line.strip()[:240]})
        if len(projects) >= 5:
            break
    return projects


def extract_experience_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    section_lines = _infer_section_lines(text, SECTION_HEADERS["experience"])
    lines = section_lines or text.splitlines()
    for line in lines:
        candidate = line.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(term in lowered for term in ("experience", "worked", "engineer", "developer", "scientist", "analyst", "lead")):
            entries.append({"detail": candidate[:240]})
        if len(entries) >= 6:
            break
    return entries


def extract_experience_timeline(text: str) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for start, end in _extract_date_ranges(text):
        if not start:
            continue
        end = end or datetime.utcnow()
        duration_months = max(0, int((end.year - start.year) * 12 + end.month - start.month))
        timeline.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_months": duration_months,
            }
        )
    return timeline[:8]


def _text_snippet(text: str, keywords: Iterable[str], limit: int = 260) -> str:
    lowered = text.lower()
    for keyword in keywords:
        idx = lowered.find(keyword.lower())
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(text), idx + limit)
            return " ".join(text[start:end].split())
    return " ".join(text[:limit].split())


def build_semantic_summary(parsed: dict[str, Any]) -> str:
    sections: list[str] = []
    if parsed.get("candidate_name"):
        sections.append(f"Candidate: {parsed['candidate_name']}")
    if parsed.get("candidate_location"):
        sections.append(f"Location: {parsed['candidate_location']}")
    if parsed.get("education_level"):
        sections.append(f"Education: {parsed['education_level']}")
    skills = parsed.get("extracted_skills") or []
    if skills:
        sections.append(f"Skills: {', '.join(skills[:20])}")
    certifications = parsed.get("certifications") or []
    if certifications:
        sections.append(f"Certifications: {', '.join(certifications[:5])}")
    projects = parsed.get("projects") or []
    if projects:
        sections.append("Projects: " + "; ".join(item.get("detail", "") for item in projects[:3]))
    experience = parsed.get("extracted_experience") or []
    if experience:
        sections.append("Experience: " + "; ".join(item.get("detail", "") for item in experience[:4]))
    timeline = parsed.get("experience_timeline") or []
    if timeline:
        total_months = sum(item.get("duration_months", 0) for item in timeline)
        sections.append(f"Experience duration: ~{round(total_months / 12, 1)} years")
    github = parsed.get("github_url")
    linkedin = parsed.get("linkedin_url")
    if github or linkedin:
        sections.append(
            "Links: "
            + ", ".join(item for item in [github, linkedin] if item)
        )
    return " | ".join(sections)[:4000]


def parse_resume_file(file_path: str) -> dict[str, Any]:
    """Parse a resume file into a structured profile."""
    raw_text = extract_text_from_file(file_path)
    candidate_name = _extract_candidate_name(raw_text)
    emails = _extract_email_list(raw_text)
    phones = _extract_phone_list(raw_text)
    github_url = _extract_github(raw_text)
    linkedin_url = _extract_linkedin(raw_text)
    candidate_email = emails[0] if emails else None
    candidate_phone = phones[0] if phones else None
    candidate_location = _extract_location(raw_text)
    extracted_skills = extract_skills(raw_text)
    extracted_education = extract_education_entries(raw_text)
    extracted_experience = extract_experience_entries(raw_text)
    certifications = extract_certifications(raw_text)
    projects = extract_projects(raw_text)
    experience_timeline = extract_experience_timeline(raw_text)
    years_of_experience = extract_years_of_experience(raw_text)
    education_level = extract_education_level(raw_text)

    parsed: dict[str, Any] = {
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "candidate_phone": candidate_phone,
        "candidate_location": candidate_location,
        "emails": emails,
        "phones": phones,
        "github_url": github_url,
        "linkedin_url": linkedin_url,
        "raw_text": raw_text,
        "extracted_skills": extracted_skills,
        "extracted_education": extracted_education,
        "extracted_experience": extracted_experience,
        "certifications": certifications,
        "projects": projects,
        "experience_timeline": experience_timeline,
        "years_of_experience": years_of_experience,
        "education_level": education_level,
        "parse_status": "done",
    }
    parsed["semantic_summary"] = build_semantic_summary(parsed)

    confidence_components = [
        0.15 if candidate_name else 0.0,
        0.15 if emails else 0.0,
        0.15 if phones else 0.0,
        min(0.2, len(extracted_skills) * 0.02),
        min(0.15, len(extracted_experience) * 0.03),
        min(0.1, len(certifications) * 0.02),
        min(0.1, len(projects) * 0.02),
    ]
    parsed["parse_confidence"] = round(min(1.0, 0.3 + sum(confidence_components)), 3)
    return parsed

