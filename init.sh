#!/bin/bash -ex

python -m venv venv
. ./venv/bin/activate \
    && pip install -U uv \
    && uv pip install -U pip \
    && uv tool install "rendercv[full]" \
    && uv pip install -e ./scoring-module

. ./venv/bin/activate \
	&& uvx linkedin-scraper-mcp@latest --login

