"""Health check endpoints."""

from __future__ import annotations

import time

import psutil
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.vector_store import get_vector_store

router = APIRouter()
START_TIME = time.time()


@router.get("/health", tags=["Health"])
async def health_check():
    """Basic health check."""
    return {"status": "healthy", "service": "HireSense AI Backend"}


@router.get("/health/detailed", tags=["Health"])
async def detailed_health():
    """Detailed health check with all subsystem statuses."""
    uptime = time.time() - START_TIME
    results = {
        "status": "healthy",
        "service": settings.APP_NAME,
        "uptime_seconds": round(uptime, 2),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "subsystems": {},
    }

    # DB check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        results["subsystems"]["database"] = "healthy"
    except Exception as e:
        results["subsystems"]["database"] = f"unhealthy: {e}"
        results["status"] = "degraded"

    # Redis check
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        results["subsystems"]["redis"] = "healthy"
    except Exception as e:
        results["subsystems"]["redis"] = f"unhealthy: {e}"
        results["status"] = "degraded"

    # Vector store check
    try:
        vector_store = get_vector_store()
        results["subsystems"]["vector_store"] = {
            "status": "healthy",
            "backend": vector_store.backend,
            "records": len(vector_store.records),
        }
    except Exception as e:
        results["subsystems"]["vector_store"] = f"unhealthy: {e}"
        results["status"] = "degraded"

    # Ollama check
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            results["subsystems"]["ollama"] = "healthy" if resp.status_code == 200 else f"unhealthy: {resp.status_code}"
            if resp.status_code != 200:
                results["status"] = "degraded"
    except Exception as e:
        results["subsystems"]["ollama"] = f"unhealthy: {e}"
        results["status"] = "degraded"

    return results
