FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONPATH=/app \
    CELERY_INCLUDE_TASKS=0

WORKDIR /app

COPY constraints.txt /tmp/constraints.txt
COPY flower/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --retries 5 --timeout 120 --prefer-binary -c /tmp/constraints.txt -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt /tmp/constraints.txt

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser workers/celery_app.py ./celery_app.py
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5555

CMD ["celery", "-A", "celery_app", "flower", "--port=5555"]
