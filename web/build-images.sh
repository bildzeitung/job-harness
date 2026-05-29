#!/usr/bin/env bash
#
# Build the job-harness web Docker images.
#
#   web/build-images.sh [all|web|runner]
#
#   all     (default) build both images
#   web     build only the lean Reflex web image (no claude CLI / creds)
#   runner  build only the agent-runner image (claude CLI + full harness)
#
# Images are tagged:
#   job-harness-web:latest
#   job-harness-agent-runner:latest
#
# The build context is the repo root (so harness-db, web, and requirements.txt
# are all reachable); .dockerignore keeps the context small.

set -euo pipefail

WEB_IMAGE="job-harness-web:latest"
RUNNER_IMAGE="job-harness-agent-runner:latest"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-all}"

build_web() {
    echo "==> Building ${WEB_IMAGE} (lean Reflex web)…"
    docker build -f "${REPO_ROOT}/web/Dockerfile" -t "${WEB_IMAGE}" "${REPO_ROOT}"
}

build_runner() {
    echo "==> Building ${RUNNER_IMAGE} (agent-runner: claude CLI + full harness)…"
    docker build -f "${REPO_ROOT}/web/runner/Dockerfile" -t "${RUNNER_IMAGE}" "${REPO_ROOT}"
}

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker is not installed or not on PATH." >&2
    exit 1
fi

case "${TARGET}" in
    all)
        build_web
        build_runner
        ;;
    web)
        build_web
        ;;
    runner)
        build_runner
        ;;
    *)
        echo "Error: unknown target '${TARGET}'. Use: all | web | runner." >&2
        exit 1
        ;;
esac

echo "==> Done. Built images:"
docker images --filter "reference=job-harness-*" --format "    {{.Repository}}:{{.Tag}}  ({{.Size}})"
