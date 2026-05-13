FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONPATH=/app \
    UPLOAD_DIR=/app/data/uploads

WORKDIR /app

# Install Python dependencies first so Docker can cache this layer.
COPY constraints.txt /tmp/constraints.txt
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --retries 5 --timeout 120 --prefer-binary -c /tmp/constraints.txt -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt /tmp/constraints.txt

# Create a non-root user for runtime.
RUN useradd --create-home --uid 10001 appuser

# Copy application code with the correct ownership.
COPY --chown=appuser:appuser backend/app /app/app

# Prepare writable data directories for SQLite fallback and uploads.
RUN mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
