# --- Backend Dockerfile (Python + FastAPI) ---
FROM python:3.10-slim

WORKDIR /app

# Clear stale proxy from Docker client config if unreachable
ARG http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" no_proxy=""
ENV http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" no_proxy=""

# Copy pre-built wheels (built on host where internet works)
COPY wheelhouse/ wheelhouse/

# Install from local wheels — no internet required inside container
RUN pip install --no-index --find-links wheelhouse/ corp_finance_monitor

# Config volume — mount your config.yaml here
VOLUME /app/data

EXPOSE 8080

CMD ["python", "-m", "corp_finance_monitor", "serve", "-c", "/app/config.yaml", "--host", "0.0.0.0", "--port", "8080"]
