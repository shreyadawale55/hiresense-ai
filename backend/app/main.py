"""HireSense AI - FastAPI Application Entry Point."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import auth, health, jobs, realtime, resumes, screening
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.rate_limit import RateLimitMiddleware
from app.services.bootstrap import ensure_initial_admin, warm_vector_store
from app.services.vector_store import get_vector_store

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting HireSense AI", version="1.0.0", environment=settings.ENVIRONMENT)
    await init_db()
    logger.info("Database initialized")
    async with AsyncSessionLocal() as session:
        await ensure_initial_admin(session)
        await warm_vector_store(session)
        await session.commit()
    logger.info("Bootstrap completed", vector_backend=get_vector_store().backend)
    yield
    logger.info("Shutting down HireSense AI")


app = FastAPI(
    title="HireSense AI API",
    description=(
        "Production-grade AI Resume Screening System aligned with SDG 8. "
        "Uses PyTorch for scoring and Mistral-7B for reasoning."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# ── Prometheus Metrics ─────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ── Request Logging Middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("Request", method=request.method, url=str(request.url))
    response = await call_next(request)
    logger.info("Response", status_code=response.status_code)
    return response


# ── Global Exception Handler ───────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), url=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["Resumes"])
app.include_router(screening.router, prefix="/api/screening", tags=["Screening"])
app.include_router(realtime.router, tags=["Realtime"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "HireSense AI",
        "version": "1.0.0",
        "sdg": "SDG 8 — Decent Work and Economic Growth",
        "docs": "/api/docs",
        "auth": "/api/auth/login",
        "ws": "/ws/screening/{job_id}",
    }
