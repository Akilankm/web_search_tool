FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PDM_CHECK_UPDATE=false \
    PYTHONPATH=/app/src

WORKDIR /app

RUN pip install --no-cache-dir pdm

COPY pyproject.toml pdm.lock* ./
RUN pdm install --prod --no-editable

COPY src ./src

RUN useradd --create-home --uid 10002 browseruser \
    && mkdir -p /data/artifacts \
    && chown -R browseruser:browseruser /app /data

USER browseruser

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=3)"

CMD ["pdm", "run", "uvicorn", "src.product_evidence_harness.browser_service.app:app", "--host", "0.0.0.0", "--port", "9000"]
