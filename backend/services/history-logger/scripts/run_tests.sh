#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICES_DIR="$(cd "${SERVICE_DIR}/.." && pwd)"

ENV_FILE="${SERVICE_DIR}/.env.test"
VENV_PY="${SERVICES_DIR}/.venv/bin/python"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Missing venv python: ${VENV_PY}" >&2
  echo "Create it with: python3 -m venv ${SERVICES_DIR}/.venv" >&2
  exit 1
fi

set -a
# Load test environment variables for local infra.
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Run history-logger tests with the shared services venv.
exec "${VENV_PY}" -m pytest "${SERVICE_DIR}" "$@"
