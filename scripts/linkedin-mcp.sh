#!/usr/bin/env bash
set -euo pipefail

exec wsl.exe docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -v "${HOME}/.linkedin-mcp:/home/pwuser/.linkedin-mcp" \
  stickerdaniel/linkedin-mcp-server:latest
