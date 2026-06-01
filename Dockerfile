# --- Backend Dockerfile (Python + FastAPI) ---
# For CI: standard pip install (internet available)
# For local: use scripts/build_wheelhouse.sh + this Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Config volume — mount your config.yaml here
VOLUME /app/data

EXPOSE 8190

CMD ["python", "-m", "corp_finance_monitor", "serve", "-c", "/app/config.yaml", "--host", "0.0.0.0", "--port", "8190"]
