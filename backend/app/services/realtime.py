"""Redis pub/sub helpers for websocket broadcasts and task notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from app.core.config import settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def publish_event(channel: str, event_type: str, payload: dict[str, Any]) -> None:
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    message = {"type": event_type, "timestamp": _utc_now(), **payload}
    try:
        await client.publish(channel, json.dumps(message))
    finally:
        await client.aclose()


async def publish_screening_event(job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    await publish_event(f"screening:{job_id}", event_type, payload)


async def publish_user_notification(user_id: str, event_type: str, payload: dict[str, Any]) -> None:
    await publish_event(f"notifications:{user_id}", event_type, payload)


async def publish_log(channel: str, message: str, *, level: str = "info", extra: dict[str, Any] | None = None) -> None:
    await publish_event(
        channel,
        "log",
        {
            "level": level,
            "message": message,
            "extra": extra or {},
        },
    )

