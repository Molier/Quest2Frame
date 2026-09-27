#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PYTHONUNBUFFERED=1
# --setup fetches verified ARM64 tools without modifying SteamOS.
if [[ "${1:-}" == "--setup" ]]; then python3 bootstrap.py; shift; fi
exec python3 server.py "$@"
