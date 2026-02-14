#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/backend/services/common/schemas"
MIRROR_DIR="${ROOT_DIR}/firmware/schemas"

source "${ROOT_DIR}/tools/runtime_schema_files.sh"

for file in "${RUNTIME_SCHEMA_FILES[@]}"; do
  src_path="${SRC_DIR}/${file}"
  mirror_path="${MIRROR_DIR}/${file}"

  if [[ ! -f "${src_path}" ]]; then
    echo "[sync_runtime_schemas] missing source file: ${src_path}" >&2
    exit 1
  fi

  cp "${src_path}" "${mirror_path}"
  echo "[sync_runtime_schemas] synced ${file}"
done

echo "[sync_runtime_schemas] done"
