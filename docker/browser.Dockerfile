FROM mcr.microsoft.com/playwright/python:v1.52.0-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10000 app || true && useradd --uid 10002 --gid 10000 --create-home app || true
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .
RUN mkdir -p /data/artifacts /tmp/browser-home && chown -R 10002:10000 /app /data /tmp/browser-home
USER 10002:10000
EXPOSE 9000
HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=3)"
CMD ["uvicorn", "product_url_v2.browser_service:app", "--host", "0.0.0.0", "--port", "9000"]
