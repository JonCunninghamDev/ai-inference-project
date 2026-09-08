#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_root}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

dependency_check='import ai_inference.demo'

if uv run --no-sync python -c "${dependency_check}" >/dev/null 2>&1; then
    echo "Demo dependencies are ready; skipping installation."
else
    echo "Demo dependencies are missing. Running the one-time installer..."
    echo "This can briefly use significant CPU, disk, and memory on older systems."
    "${script_dir}/install_dependencies.sh"
fi

echo "Starting the local demo..."
echo "  Guided walkthrough: http://127.0.0.1:8080/"
echo "  Interactive Swagger: http://127.0.0.1:8080/docs"
echo "  Health endpoint:     http://127.0.0.1:8080/health"
exec uv run --no-sync python -m ai_inference.demo "$@"
