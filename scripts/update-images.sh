#!/bin/bash -ex
#
# Update the docker images this harness users
#

docker pull mcp/sqlite:latest
docker pull stickerdaniel/linkedin-mcp-server
docker pull minlag/mermaid-cli:latest

