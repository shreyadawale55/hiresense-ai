"""SQLAlchemy ORM model for Resume submissions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Candidate info
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=True)
    candidate_email: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    candidate_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    candidate_location: Mapped[str] = mapped_column(String(255), nullable=True)
    emails: Mapped[list] = mapped_column(JSON, default=list)
    phones: Mapped[list] = mapped_column(JSON, default=list)
    github_url: Mapped[str] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # File metadata
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf | docx
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)

    # Parsed content
    raw_text: Mapped[str] = mapped_column(Text, nullable=True)
    extracted_skills: Mapped[list] = mapped_column(JSON, default=list)
    extracted_education: Mapped[list] = mapped_column(JSON, default=list)
    extracted_experience: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    experience_timeline: Mapped[list] = mapped_column(JSON, default=list)
    years_of_experience: Mapped[float] = mapped_column(Float, default=0.0)
    education_level: Mapped[str] = mapped_column(String(100), nullable=True)
    semantic_summary: Mapped[str] = mapped_column(Text, nullable=True)
    parse_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # NLP embeddings stored as JSON (for caching)
    embedding_vector: Mapped[list] = mapped_column(JSON, nullable=True)

    # Processing state
    parse_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | processing | done | failed
    parse_error: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    screenings: Mapped[list["Screening"]] = relationship(  # noqa: F821
        back_populates="resume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} name={self.candidate_name!r}>"
