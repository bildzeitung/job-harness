#!/bin/bash -ex
#
# Install 3rd party tools used in this project
#

# Ollama
#
curl -fsSL https://ollama.com/install.sh | sh
ollama -v
ollama pull qwen3-embedding:0.6b

