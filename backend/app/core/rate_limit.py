"""Redis-backed rate limiting middleware."""

from __future__ import annotations

import time
from typing import Iterable

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple fixed-window rate limiting with Redis as the backend."""

    def __init__(self, app: ASGIApp, *, skip_paths: Iterable[str] | None = None):
        super().__init__(app)
        self.skip_paths = set(skip_paths or ())

    def _window_for_path(self, path: str) -> int:
        if path.startswith("/api/resumes/upload"):
            return settings.RATE_LIMIT_UPLOADS_PER_MINUTE
        if path.startswith("/api/auth/login"):
            return 20
        return settings.RATE_LIMIT_REQUESTS_PER_MINUTE

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or path in self.skip_paths
            or path.startswith("/health")
            or path.startswith("/metrics")
            or path.startswith("/api/docs")
            or path.startswith("/api/openapi")
            or path.startswith("/api/redoc")
            or path.startswith("/ws")
        ):
            return await call_next(request)

        client_ip = request.headers.get("x-forwarded-for")
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        limit = self._window_for_path(path)
        window_seconds = 60
        bucket = int(time.time() // window_seconds)
        key = f"rate:{client_ip}:{path}:{bucket}"

        try:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, window_seconds)
            ttl = await redis_client.ttl(key)
            await redis_client.aclose()
        except Exception:
            # Fail open if Redis is temporarily unavailable.
            return await call_next(request)

        remaining = max(0, limit - count)
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(max(ttl, 0)),
        }
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response

