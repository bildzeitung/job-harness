#!/bin/bash -ex
#
# Spawn a login window for the LinkedIn MCP server
#

. ./venv/bin/activate &&
	uvx linkedin-scraper-mcp@latest --login

