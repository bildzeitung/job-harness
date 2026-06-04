#!/bin/bash -ex
#
# Install 3rd party tools used in this project
#

# RTK (https://github.com/rtk-ai/rtk)
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# Ollama
#
curl -fsSL https://ollama.com/install.sh | sh
ollama -v
ollama pull qwen3-embedding:0.6b

