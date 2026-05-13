FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONPATH=/app \
    CELERY_INCLUDE_TASKS=1

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY constraints.txt /tmp/constraints.txt
COPY workers/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu --retries 5 --timeout 120 --prefer-binary -c /tmp/constraints.txt -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt /tmp/constraints.txt

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser backend/app ./app
COPY --chown=appuser:appuser workers/celery_app.py ./celery_app.py
COPY --chown=appuser:appuser workers/tasks ./tasks

RUN mkdir -p /app/uploads /app/models /app/data
RUN chown -R appuser:appuser /app

# Default: worker. Override in docker-compose for beat/flower.
USER appuser
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", \
     "--concurrency=4", "-Q", "default,ai_scoring,llm_explain"]
