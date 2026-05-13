"""Lightweight Celery application configuration without task auto-imports."""

from __future__ import annotations

import os

from celery import Celery
from kombu import Exchange, Queue
import structlog

logger = structlog.get_logger(__name__)

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
INCLUDE_TASKS = os.environ.get("CELERY_INCLUDE_TASKS", "0").strip().lower() in {"1", "true", "yes", "on"}
TASK_MODULES = [
    "tasks.resume_parser",
    "tasks.ai_scorer",
    "tasks.llm_explainer",
]

app = Celery(
    "hiresense",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=TASK_MODULES if INCLUDE_TASKS else [],
)

default_exchange = Exchange("default", type="direct")
ai_exchange = Exchange("ai_scoring", type="direct")
llm_exchange = Exchange("llm_explain", type="direct")

app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("ai_scoring", ai_exchange, routing_key="ai_scoring"),
    Queue("llm_explain", llm_exchange, routing_key="llm_explain"),
)
app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

app.conf.task_routes = {
    "tasks.resume_parser.*": {"queue": "default"},
    "tasks.ai_scorer.*": {"queue": "ai_scoring"},
    "tasks.llm_explainer.*": {"queue": "llm_explain"},
}

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=86400,
    result_persistent=True,
    task_max_retries=3,
    task_default_retry_delay=30,
    worker_send_task_events=True,
    task_send_sent_event=True,
    timezone="UTC",
    enable_utc=True,
)
