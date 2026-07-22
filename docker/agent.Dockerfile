FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10000 app && useradd --uid 10001 --gid 10000 --create-home app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY feature_sets ./feature_sets
RUN python -m pip install --upgrade pip && python -m pip install .
RUN mkdir -p /data/artifacts && chown -R 10001:10000 /app /data
USER 10001:10000
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "product_url_v2.api:app", "--host", "0.0.0.0", "--port", "8000"]
