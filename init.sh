#!/bin/bash -ex

python -m venv venv
. ./venv/bin/activate \
    && pip install -U uv \
    && uv pip install -r requirements.txt

