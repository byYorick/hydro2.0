#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ERD_MMD="${REPO_ROOT}/backend/laravel/erd.mmd"
ERD_SVG="${REPO_ROOT}/backend/laravel/erd.svg"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; install Docker or run in a dev container." >&2
  exit 1
fi

if [[ ! -f "${ERD_MMD}" ]]; then
  echo "Missing input file: ${ERD_MMD}" >&2
  exit 1
fi

IMAGE="${MERMAID_CLI_IMAGE:-ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:latest}"

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "${REPO_ROOT}:/data" \
  "${IMAGE}" \
  -i /data/backend/laravel/erd.mmd \
  -o /data/backend/laravel/erd.svg

echo "Generated ${ERD_SVG}"
