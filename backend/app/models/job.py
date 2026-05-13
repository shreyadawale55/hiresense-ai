"""SQLAlchemy ORM model for Job postings."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    DRAFT = "draft"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    experience_years_min: Mapped[int] = mapped_column(default=0)
    experience_years_max: Mapped[int] = mapped_column(default=20)
    education_level: Mapped[str] = mapped_column(String(100), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    salary_min: Mapped[float] = mapped_column(nullable=True)
    salary_max: Mapped[float] = mapped_column(nullable=True)
    job_type: Mapped[str] = mapped_column(String(50), default="full-time")
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.ACTIVE
    )
    # SDG 8: track fairness metrics
    diversity_goal: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    created_by: Mapped["User"] = relationship(back_populates="jobs")  # noqa: F821
    screenings: Mapped[list["Screening"]] = relationship(  # noqa: F821
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title={self.title!r}>"
