FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

WORKDIR /app

COPY constraints.txt /tmp/constraints.txt
COPY ai_models/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu --retries 5 --timeout 120 --prefer-binary -c /tmp/constraints.txt -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt /tmp/constraints.txt

COPY ai_models/. /app
RUN mkdir -p /app/models /app/data

EXPOSE 8001

CMD ["uvicorn", "inference.scorer:app", "--host", "0.0.0.0", "--port", "8001"]
