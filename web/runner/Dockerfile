# agent-runner image: the ONLY container with the claude CLI + credentials.
# Build context is the repo root (see web/docker-compose.yml).
# Installs the full harness so spawned subagents (job-scorer, job-preparer ->
# resume-tailor/rendercv/cover-letter-creator) can actually run.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    REPO_DIR=/repo \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the claude CLI (provides the `claude` binary used to run agents).
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /repo
COPY . /repo
# Full harness deps (rendercv, scoring, etc.) so the preparer pipeline works,
# plus the SSE service deps.
RUN uv pip install -r /repo/requirements.txt \
    && uv pip install "/repo/web[runner]"

EXPOSE 8100
CMD ["uvicorn", "app:app", "--app-dir", "/repo/web/runner", "--host", "0.0.0.0", "--port", "8100"]
