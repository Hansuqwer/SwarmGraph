#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 path/to/audit.jsonl [SECRET_ENV]" >&2
  exit 2
fi

LOG_PATH="$1"
SECRET_ENV="${2:-HIVE_SWARM_AUDIT_SECRET}"
uv run ai-provider-gateway audit verify "$LOG_PATH" --secret-env "$SECRET_ENV"
