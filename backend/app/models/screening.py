"""SQLAlchemy ORM model for AI Screening results."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign keys
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )

    # Celery task IDs for async tracking
    parse_task_id: Mapped[str] = mapped_column(String(255), nullable=True)
    score_task_id: Mapped[str] = mapped_column(String(255), nullable=True)
    explain_task_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Scoring (0-100)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    skill_match_score: Mapped[float] = mapped_column(Float, nullable=True)
    experience_score: Mapped[float] = mapped_column(Float, nullable=True)
    education_score: Mapped[float] = mapped_column(Float, nullable=True)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)

    # Skill breakdown
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    bonus_skills: Mapped[list] = mapped_column(JSON, default=list)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

    # LLM Explanation
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=True)
    ai_recommendation: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # strong_yes | yes | maybe | no
    ai_strengths: Mapped[list] = mapped_column(JSON, default=list)
    ai_concerns: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_context: Mapped[list] = mapped_column(JSON, default=list)
    explanation_context: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_model: Mapped[str] = mapped_column(String(120), nullable=True)

    # SDG 8 — Fairness
    fairness_flags: Mapped[list] = mapped_column(JSON, default=list)
    bias_keywords: Mapped[list] = mapped_column(JSON, default=list)
    bias_detected: Mapped[bool] = mapped_column(default=False)
    fairness_score: Mapped[float] = mapped_column(Float, nullable=True)

    # Processing state
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | processing | scored | explained | failed
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=True)

    # Ranking
    rank: Mapped[int] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="screenings")  # noqa: F821
    resume: Mapped["Resume"] = relationship(back_populates="screenings")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Screening id={self.id} score={self.overall_score}>"
