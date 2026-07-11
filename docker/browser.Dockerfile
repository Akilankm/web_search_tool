FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOME=/tmp/browser-home

WORKDIR /app

COPY requirements/browser.txt /tmp/browser-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/browser-requirements.txt

COPY src ./src

RUN groupadd --gid 10000 evidence \
    && useradd --create-home --uid 10002 --gid evidence browseruser \
    && mkdir -p /data/artifacts /tmp/browser-home \
    && chown -R browseruser:evidence /app /data /tmp/browser-home

USER browseruser

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "src.product_evidence_harness.browser_service.app:app", "--host", "0.0.0.0", "--port", "9000"]
