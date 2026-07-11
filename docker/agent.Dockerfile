FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PDM_CHECK_UPDATE=false \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pdm

COPY pyproject.toml pdm.lock* ./
RUN pdm install --prod --no-editable

COPY src ./src
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 agentuser \
    && mkdir -p /data/artifacts /data/private \
    && chown -R agentuser:agentuser /app /data

USER agentuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["pdm", "run", "uvicorn", "src.product_evidence_harness.agent_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
