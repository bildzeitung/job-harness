# Lean Reflex web image for the job-harness UI.
# Build context is the repo root (see web/docker-compose.yml).
# Carries NO claude CLI and NO credentials — agent runs are delegated to the
# separate agent-runner service via RUNNER_URL.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PATH="/root/.local/bin:${PATH}"

# curl/unzip: Reflex bootstraps its bundled Bun toolchain on init.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app
COPY harness-db /app/harness-db
COPY web /app/web
RUN uv pip install /app/harness-db /app/web

WORKDIR /app/web
# Pre-fetch the Bun toolchain and pre-build the production frontend at image
# build time so startup is fast and needs no network.
RUN reflex init && reflex export --frontend-only --no-zip

# 3000 = frontend, 8000 = backend (WebSocket/event API).
EXPOSE 3000 8000
CMD ["reflex", "run", "--env", "prod"]
