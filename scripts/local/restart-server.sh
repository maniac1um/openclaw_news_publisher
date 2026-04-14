#!/usr/bin/env bash
# Restart local OpenClaw News Publisher.
# Safe to commit: no machine-specific paths or secrets.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/stop-server.sh"
sleep 1
"$DIR/start-server.sh"
