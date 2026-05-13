"""
HireSense AI — PyTorch Inference REST Service
Served via FastAPI on port 8001
Endpoint: POST /score  →  { score: float, breakdown: {...} }
"""

import os, json, logging, re, math, hashlib
from pathlib import Path
from typing import List, Optional
import numpy as np
import torch
import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from trainer.model import ResumeScorerNet

logger = logging.getLogger(__name__)
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))


def _resolve_device() -> str:
    requested = os.environ.get("DEVICE")
    if requested == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA requested but unavailable; falling back to CPU")
        return "cpu"
    if requested:
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


DEVICE = _resolve_device()

app = FastAPI(title="HireSense AI Scorer", version="1.0.0")

# ── Load model artifacts at startup ─────────────────────────────────────────
_model: Optional[ResumeScorerNet] = None
_vectorizer = None
_label_encoder = None
_taxonomy: dict = {}
_embedder = None


@app.on_event("startup")
def load_artifacts():
    global _model, _vectorizer, _label_encoder, _taxonomy
    model_path = MODEL_DIR / "resume_scorer.pt"
    vec_path = MODEL_DIR / "tfidf_vectorizer.pkl"
    enc_path = MODEL_DIR / "label_encoder.pkl"
    tax_path = MODEL_DIR / "category_taxonomy.json"

    if not model_path.exists():
        logger.warning("Model not trained yet — scorer running in mock mode")
        return

    _model = ResumeScorerNet.from_checkpoint(str(model_path), device=DEVICE)
    _vectorizer = joblib.load(vec_path)
    _label_encoder = joblib.load(enc_path)
    with open(tax_path) as f:
        _taxonomy = json.load(f)
    logger.info(f"Scorer loaded: {len(_taxonomy)} categories, device={DEVICE}")


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    except Exception:
        _embedder = False
    return _embedder


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9+#.]+", (text or "").lower()) if len(token) > 2}


def _semantic_similarity(resume_text: str, job_context: str) -> float:
    embedder = _get_embedder()
    if embedder:
        try:
            vectors = embedder.encode([resume_text, job_context], normalize_embeddings=True)
            left, right = vectors[0], vectors[1]
            if hasattr(left, "tolist"):
                left = left.tolist()
            if hasattr(right, "tolist"):
                right = right.tolist()
            return float(max(0.0, min(1.0, np.dot(left, right))))
        except Exception:
            pass
    left = _token_set(resume_text)
    right = _token_set(job_context)
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left | right), 1)


# ── Request / Response schemas ───────────────────────────────────────────────
class ScoreRequest(BaseModel):
    resume_text: str
    job_category: str
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    years_experience_required: int = 0
    resume_years_experience: float = 0.0
    resume_education_level: str = ""
    required_education_level: str = ""


class ScoreResponse(BaseModel):
    overall_score: float
    skill_match_score: float
    experience_score: float
    education_score: float
    semantic_score: float
    confidence_score: float
    matched_skills: List[str]
    missing_skills: List[str]
    bonus_skills: List[str]
    category_probabilities: dict


def _score_skills(resume_text: str, required: List[str], preferred: List[str]):
    text_lower = resume_text.lower()
    matched = [s for s in required if s.lower() in text_lower]
    missing = [s for s in required if s.lower() not in text_lower]
    bonus = [s for s in preferred if s.lower() in text_lower]
    req_score = (len(matched) / max(len(required), 1)) * 100
    pref_bonus = min(10, len(bonus) * 2)
    return min(100, req_score + pref_bonus), matched, missing, bonus


def _score_experience(resume_years: float, required_years: int) -> float:
    if required_years == 0:
        return 100.0
    ratio = resume_years / required_years
    if ratio >= 1.0:
        return min(100.0, 80 + min(20, (ratio - 1.0) * 10))
    return max(0, ratio * 80)


EDUCATION_HIERARCHY = {"phd": 4, "master": 3, "bachelor": 2, "associate": 1, "high school": 0}


def _score_education(resume_edu: str, required_edu: str) -> float:
    if not required_edu:
        return 100.0
    r_level = next((v for k, v in EDUCATION_HIERARCHY.items() if k in resume_edu.lower()), 0)
    j_level = next((v for k, v in EDUCATION_HIERARCHY.items() if k in required_edu.lower()), 0)
    if r_level >= j_level:
        return 100.0
    return max(40.0, 100.0 - (j_level - r_level) * 25)


@app.post("/score", response_model=ScoreResponse)
def score_resume(req: ScoreRequest):
    # Skill scoring (always available)
    skill_score, matched, missing, bonus = _score_skills(
        req.resume_text, req.required_skills, req.preferred_skills
    )
    exp_score = _score_experience(req.resume_years_experience, req.years_experience_required)
    edu_score = _score_education(req.resume_education_level, req.required_education_level)
    job_context = " ".join(
        part for part in [
            req.job_category,
            " ".join(req.required_skills or []),
            " ".join(req.preferred_skills or []),
        ] if part
    )
    semantic_score = round(_semantic_similarity(req.resume_text, job_context) * 100.0, 2)

    # ML model scoring (if model is loaded)
    cat_probs = {}
    if _model and _vectorizer:
        features = _vectorizer.transform([req.resume_text]).toarray().astype(np.float32)
        feat_tensor = torch.tensor(features).to(DEVICE)
        probs = _model.get_probabilities(feat_tensor)[0]
        cat_probs = {_taxonomy.get(str(i), str(i)): round(p.item() * 100, 2)
                     for i, p in enumerate(probs)}
        # Find target category prob
        target_idx = None
        for i, name in _taxonomy.items():
            if req.job_category.lower() in name.lower():
                target_idx = int(i)
                break
        if target_idx is not None:
            model_score = _model.get_match_score(feat_tensor, target_idx)
            # Blend semantic retrieval with model + structured signals
            overall = 0.35 * model_score + 0.25 * semantic_score + 0.2 * skill_score + 0.1 * exp_score + 0.1 * edu_score
        else:
            overall = 0.35 * semantic_score + 0.25 * skill_score + 0.2 * exp_score + 0.1 * edu_score + 0.1 * 50
    else:
        # Fallback without ML model
        overall = 0.4 * semantic_score + 0.3 * skill_score + 0.2 * exp_score + 0.1 * edu_score

    confidence = max(0.0, min(1.0, 0.45 + semantic_score / 250.0 + len(matched) * 0.02 - len(missing) * 0.01))

    return ScoreResponse(
        overall_score=round(overall, 2),
        skill_match_score=round(skill_score, 2),
        experience_score=round(exp_score, 2),
        education_score=round(edu_score, 2),
        semantic_score=round(semantic_score, 2),
        confidence_score=round(confidence, 3),
        matched_skills=matched,
        missing_skills=missing,
        bonus_skills=bonus,
        category_probabilities=cat_probs,
    )


@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": _model is not None, "device": DEVICE}


@app.get("/categories")
def get_categories():
    return {"categories": list(_taxonomy.values())}
