FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10000 app && useradd --uid 10003 --gid 10000 --create-home app
COPY pyproject.toml README.md ./
COPY src ./src
COPY apps ./apps
RUN python -m pip install --upgrade pip && python -m pip install .
USER 10003:10000
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "apps/product_url_ui.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
