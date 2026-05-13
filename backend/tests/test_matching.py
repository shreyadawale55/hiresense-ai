from __future__ import annotations

from types import SimpleNamespace

import app.services.matching as matching


def test_score_resume_against_job_hybrid_score(monkeypatch):
    monkeypatch.setattr(matching, "semantic_similarity", lambda left, right: 0.87)

    job = SimpleNamespace(
        title="Machine Learning Engineer",
        company="HireSense AI",
        description="Build semantic search, vector retrieval, and ML pipelines.",
        requirements="Python, FastAPI, Docker, PyTorch, and PostgreSQL.",
        required_skills=["Python", "FastAPI", "Docker", "PyTorch"],
        preferred_skills=["SentenceTransformers", "FAISS"],
        experience_years_min=2,
        education_level="Bachelor's",
    )
    resume = {
        "candidate_name": "Avery Singh",
        "candidate_location": "Bengaluru",
        "extracted_skills": ["Python", "FastAPI", "Docker", "PyTorch", "FAISS"],
        "years_of_experience": 3.5,
        "education_level": "Bachelor's",
        "semantic_summary": "Built FastAPI systems with PyTorch and FAISS for semantic retrieval.",
        "projects": [{"detail": "Built a vector search platform with FAISS and RAG."}],
        "certifications": ["AWS Certified ML Specialty"],
        "experience_timeline": [{"start": "2022", "end": "Present"}],
    }

    result = matching.score_resume_against_job(job, resume)

    assert result["overall_score"] > 70
    assert result["semantic_score"] == 87.0
    assert result["recommendation"] in {"strong_yes", "yes"}
    assert "Python" in result["matched_skills"]
    assert result["confidence_score"] > 0
