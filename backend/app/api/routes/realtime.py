"""WebSocket endpoints for live screening progress and notifications."""

from __future__ import annotations

import asyncio
import json
from typing import Any
import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.job import Job
from app.models.user import User

router = APIRouter()


async def _authenticate(token: str) -> User:
    claims = decode_token(token)
    if claims.get("type") != "access":
        raise ValueError("Access token required")
    user_id = claims.get("uid") or claims.get("sub")
    if not user_id:
        raise ValueError("Invalid token")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise ValueError("Inactive user")
        return user


async def _authorize_job_access(user: User, job_id: uuid.UUID) -> None:
    if user.role.value == "admin":
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job or job.created_by_id != user.id:
            raise ValueError("Unauthorized channel")


async def _stream_channel(websocket: WebSocket, channel: str) -> None:
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                data = message.get("data")
                try:
                    payload = json.loads(data)
                except Exception:
                    payload = {"type": "raw", "data": data}
                await websocket.send_json(payload)
            await asyncio.sleep(0.15)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        finally:
            await client.aclose()


@router.websocket("/ws/screening/{job_id}")
async def ws_screening(websocket: WebSocket, job_id: uuid.UUID):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        user = await _authenticate(token)
        await _authorize_job_access(user, job_id)
    except Exception:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    await websocket.send_json({"type": "connection", "channel": f"screening:{job_id}", "status": "connected"})
    await _stream_channel(websocket, f"screening:{job_id}")


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        user = await _authenticate(token)
    except Exception:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    await websocket.send_json({"type": "connection", "channel": f"notifications:{user.id}", "status": "connected"})
    await _stream_channel(websocket, f"notifications:{user.id}")

