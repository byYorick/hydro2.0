#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/backend/services/common/schemas"
MIRROR_DIR="${ROOT_DIR}/firmware/schemas"

source "${ROOT_DIR}/tools/runtime_schema_files.sh"

failed=0

for file in "${RUNTIME_SCHEMA_FILES[@]}"; do
  src_path="${SRC_DIR}/${file}"
  mirror_path="${MIRROR_DIR}/${file}"

  if [[ ! -f "${src_path}" ]]; then
    echo "[runtime_schema_parity] missing source file: ${src_path}" >&2
    failed=1
    continue
  fi

  if [[ ! -f "${mirror_path}" ]]; then
    echo "[runtime_schema_parity] missing mirror file: ${mirror_path}" >&2
    failed=1
    continue
  fi

  src_hash="$(sha256sum "${src_path}" | awk '{print $1}')"
  mirror_hash="$(sha256sum "${mirror_path}" | awk '{print $1}')"

  if [[ "${src_hash}" != "${mirror_hash}" ]]; then
    echo "[runtime_schema_parity] mismatch: ${file}" >&2
    echo "  source hash: ${src_hash}" >&2
    echo "  mirror hash: ${mirror_hash}" >&2
    diff -u "${src_path}" "${mirror_path}" || true
    failed=1
  fi
done

if [[ "${failed}" -ne 0 ]]; then
  echo "[runtime_schema_parity] FAILED. Run: ./tools/sync_runtime_schemas.sh" >&2
  exit 1
fi

echo "[runtime_schema_parity] OK"
