FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOME=/tmp/agent-home

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/agent.txt /tmp/agent-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/agent-requirements.txt

COPY src ./src
COPY scripts ./scripts

RUN groupadd --gid 10000 evidence \
    && useradd --create-home --uid 10001 --gid evidence agentuser \
    && mkdir -p /data/artifacts /data/private /tmp/agent-home \
    && chown -R agentuser:evidence /app /data /tmp/agent-home

USER agentuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "src.product_evidence_harness.agent_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
