#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${JOB_DATA_ROOT:-}" ]]; then
  echo "Error: JOB_DATA_ROOT is not set" >&2
  exit 1
fi

exec wsl.exe docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -v "${JOB_DATA_ROOT}/jobs:/mcp" \
  mcp/sqlite \
  --db-path /mcp/postings.db
