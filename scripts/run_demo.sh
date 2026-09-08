#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_root}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

echo "Ensuring runtime dependencies are installed..."
uv sync --extra dev --extra test

echo "Starting the local demo at http://127.0.0.1:8080..."
uv run python -m ai_inference.demo "$@"
