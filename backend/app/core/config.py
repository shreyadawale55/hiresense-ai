"""Application configuration using Pydantic Settings."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


def _sqlite_async_url() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{(DATA_DIR / 'hiresense_db.sqlite').resolve().as_posix()}"


def _can_connect(url_value: str) -> bool:
    """Check whether a database host/port is reachable."""
    try:
        url = make_url(url_value)
    except Exception:
        return False

    host = url.host
    if not host:
        return False

    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _local_upload_dir() -> str:
    uploads = DATA_DIR / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return str(uploads)


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "HireSense AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    TOKEN_ISSUER: str = "hiresense-ai"
    TOKEN_AUDIENCE: str = "hiresense-users"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://hiresense:hiresense_secret_change_me@localhost:5432/hiresense_db"
    )

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Auth bootstrap
    INITIAL_ADMIN_EMAIL: str = "admin@hiresense.ai"
    INITIAL_ADMIN_PASSWORD: str = "ChangeMe123!"
    INITIAL_ADMIN_FULL_NAME: str = "HireSense Admin"
    INITIAL_ADMIN_ROLE: str = "admin"

    # Security
    PASSWORD_HASH_ROUNDS: int = 200_000
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 10
    RATE_LIMIT_BURST: int = 20

    # AI / Semantic Search
    MODEL_PATH: str = "/app/models/resume_scorer.pt"
    MODEL_VERSION: str = "v2.0.0"
    DEVICE: str = "cpu"
    MODEL_PORT: int = 8001
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_BACKEND: str = "memory"  # memory | faiss | chroma
    VECTOR_INDEX_PATH: str = "/app/data/vector.index"
    VECTOR_METADATA_PATH: str = "/app/data/vector_meta.json"

    # LLM
    OLLAMA_URL: str = "http://ollama:11434"
    LLM_MODEL: str = "mistral:7b"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT: int = 120

    # File Upload
    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "docx"]

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:80"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        return _parse_list(v)

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def assemble_allowed_extensions(cls, v):
        return _parse_list(v) or ["pdf", "docx"]

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, v):
        if isinstance(v, str):
            value = v.strip().lower()
            if value in {"1", "true", "yes", "on", "debug"}:
                return True
            if value in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def resolve_database_url(cls, v):
        if not v or not isinstance(v, str):
            return _sqlite_async_url()
        if v.startswith("sqlite"):
            return v

        environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        if environment != "production" and v.startswith("postgres"):
            if _can_connect(v):
                return v
            return _sqlite_async_url()
        return v

    @field_validator("UPLOAD_DIR", mode="before")
    @classmethod
    def resolve_upload_dir(cls, v):
        if not v or not isinstance(v, str):
            return _local_upload_dir()

        upload_path = Path(v)
        if v.startswith("/app") and not Path("/app").exists():
            return _local_upload_dir()
        try:
            upload_path.mkdir(parents=True, exist_ok=True)
            return str(upload_path)
        except OSError:
            return _local_upload_dir()

    @field_validator("VECTOR_BACKEND", mode="before")
    @classmethod
    def normalize_vector_backend(cls, v):
        backend = (v or "memory").strip().lower()
        if backend not in {"memory", "faiss", "chroma"}:
            return "memory"
        return backend

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, v):
        return (v or "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT in {"production", "prod"}


settings = Settings()
