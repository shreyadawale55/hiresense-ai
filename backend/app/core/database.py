"""Async SQLAlchemy database configuration."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _parse_database_url(database_url: str | None = None):
    raw_url = database_url or settings.DATABASE_URL
    return make_url(raw_url)


def get_database_url_info(database_url: str | None = None) -> dict[str, Any]:
    """Return a sanitized summary of the resolved database URL."""
    url = _parse_database_url(database_url)
    return {
        "drivername": url.drivername,
        "backend": url.get_backend_name(),
        "username": url.username,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "rendered_url": url.render_as_string(hide_password=True),
    }


def get_sync_database_url(database_url: str | None = None) -> str:
    """Convert the configured async database URL into a sync SQLAlchemy URL."""
    url = _parse_database_url(database_url)
    backend = url.get_backend_name()
    if backend == "sqlite":
        sync_url = url.set(drivername="sqlite")
    else:
        sync_url = url.set(drivername="postgresql")
    return sync_url.render_as_string(hide_password=False)


def log_database_configuration(prefix: str = "Resolved database configuration") -> dict[str, Any]:
    """Log the active database target without exposing secrets."""
    info = get_database_url_info()
    logger.info(prefix, **info)
    if info["backend"] == "postgresql" and info["database"] == "hiresense":
        logger.warning(
            "Database name still resolves to the legacy default 'hiresense'; expected 'hiresense_db'",
            expected_database="hiresense_db",
            resolved_database=info["database"],
        )
    return info


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {
            "echo": settings.DEBUG,
            "connect_args": {"check_same_thread": False},
        }
    return {
        "echo": settings.DEBUG,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }


engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


_SCHEMA_UPGRADES: dict[str, list[tuple[str, str]]] = {
    "jobs": [
        ("created_by_id", "UUID"),
        ("semantic_summary", "TEXT"),
        ("search_document", "TEXT"),
    ],
    "resumes": [
        ("emails", "JSON"),
        ("phones", "JSON"),
        ("github_url", "VARCHAR(500)"),
        ("linkedin_url", "VARCHAR(500)"),
        ("certifications", "JSON"),
        ("projects", "JSON"),
        ("experience_timeline", "JSON"),
        ("semantic_summary", "TEXT"),
        ("parse_confidence", "FLOAT DEFAULT 0.0"),
    ],
    "screenings": [
        ("semantic_score", "FLOAT"),
        ("confidence_score", "FLOAT"),
        ("score_breakdown", "JSON"),
        ("retrieved_context", "JSON"),
        ("explanation_context", "JSON"),
        ("llm_model", "VARCHAR(120)"),
        ("bias_keywords", "JSON"),
        ("fairness_score", "FLOAT"),
        ("query_text", "TEXT"),
    ],
}


async def _ensure_schema(conn) -> None:
    """Lightweight schema migration for existing databases."""

    def _sync_upgrade(sync_conn):
        inspector = inspect(sync_conn)
        existing_tables = set(inspector.get_table_names())
        for table_name, columns in _SCHEMA_UPGRADES.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_ddl in columns:
                if column_name in existing_columns:
                    continue
                sync_conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}'))
                logger.info("Added missing column", table=table_name, column=column_name)

    await conn.run_sync(_sync_upgrade)


async def init_db():
    """Create all tables on startup."""
    try:
        log_database_configuration()
        async with engine.begin() as conn:
            from app.models import job, notification, refresh_token, resume, screening, user  # noqa: F401

            await conn.run_sync(Base.metadata.create_all)
            await _ensure_schema(conn)
        logger.info("Database tables created/verified")
    except Exception:
        logger.exception("Database initialization failed")
        raise


async def get_db():
    """Dependency: yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
