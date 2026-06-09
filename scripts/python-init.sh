#!/bin/bash -ex
#
# Just initialize the Python environment
#
# Run from root directory. Installs all needed Python for this project.
#
python -m venv venv
. ./venv/bin/activate \
    && pip install -U uv \
    && uv pip install -r requirements.txt

