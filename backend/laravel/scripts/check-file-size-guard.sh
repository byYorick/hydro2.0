#!/usr/bin/env bash
set -euo pipefail

MAX_LINES="${MAX_FILE_LINES:-900}"
MAX_INCREASE="${MAX_FILE_LINES_INCREASE:-30}"
EXCEPTIONS_FILE="${FILE_SIZE_GUARD_EXCEPTIONS_FILE:-backend/laravel/scripts/file-size-guard-exceptions.txt}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "$REPO_ROOT"

MODE="ci"
BASE_REF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --working-tree)
      MODE="working-tree"
      shift
      ;;
    --base)
      BASE_REF="${2:-}"
      shift 2
      ;;
    *)
      echo "[file-size-guard] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

resolve_base_ref() {
  if [[ -n "$BASE_REF" ]]; then
    echo "$BASE_REF"
    return
  fi

  if [[ -n "${GITHUB_BASE_REF:-}" ]] && git show-ref --verify --quiet "refs/remotes/origin/${GITHUB_BASE_REF}"; then
    git merge-base HEAD "origin/${GITHUB_BASE_REF}"
    return
  fi

  if git show-ref --verify --quiet "refs/remotes/origin/main"; then
    git merge-base HEAD origin/main
    return
  fi

  if git rev-parse --verify --quiet HEAD~1 >/dev/null; then
    git rev-parse HEAD~1
    return
  fi

  git rev-parse HEAD
}

is_target_file() {
  local file="$1"

  if [[ "$file" =~ ^backend/laravel/(app|config|routes|tests)/.+\.php$ ]]; then
    return 0
  fi

  if [[ "$file" =~ ^backend/laravel/resources/js/.+\.(ts|tsx|js|vue)$ ]]; then
    return 0
  fi

  if [[ "$file" =~ ^backend/laravel/scripts/.+\.sh$ ]]; then
    return 0
  fi

  return 1
}

get_changed_files() {
  if [[ "$MODE" == "working-tree" ]]; then
    {
      git diff --name-only --diff-filter=ACMR HEAD
      git ls-files --others --exclude-standard
    } | sort -u
    return
  fi

  local base
  base="$BASE_REF"

  if [[ "$base" == "$(git rev-parse HEAD)" ]]; then
    git diff-tree --no-commit-id --name-only --diff-filter=ACMR -r HEAD
    return
  fi

  git diff --name-only --diff-filter=ACMR "$base...HEAD"
}

trim_space() {
  tr -d '[:space:]'
}

get_exception_limit() {
  local file="$1"
  local normalized_file="$file"
  local exceptions_path="${REPO_ROOT}/${EXCEPTIONS_FILE}"

  if [[ ! -f "$exceptions_path" ]]; then
    return 1
  fi

  while IFS='|' read -r pattern limit; do
    pattern="$(echo -n "${pattern:-}" | xargs || true)"
    limit="$(echo -n "${limit:-}" | xargs || true)"

    if [[ -z "$pattern" ]] || [[ "$pattern" =~ ^# ]]; then
      continue
    fi

    if [[ "$normalized_file" == "$pattern" ]]; then
      if [[ "$limit" =~ ^[0-9]+$ ]]; then
        echo "$limit"
        return 0
      fi
      return 1
    fi
  done < "$exceptions_path"

  return 1
}

if [[ "$MODE" == "working-tree" ]]; then
  BASE_REF="HEAD"
else
  BASE_REF="$(resolve_base_ref)"
fi

mapfile -t changed_files < <(get_changed_files)

if [[ "${#changed_files[@]}" -eq 0 ]]; then
  echo "[file-size-guard] Нет измененных файлов для проверки"
  exit 0
fi

violations=()
checked=0

echo "[file-size-guard] MAX_FILE_LINES=${MAX_LINES}, MAX_FILE_LINES_INCREASE=${MAX_INCREASE}, mode=${MODE}"
if [[ -n "$BASE_REF" ]]; then
  echo "[file-size-guard] base=${BASE_REF}"
fi

for file in "${changed_files[@]}"; do
  if ! is_target_file "$file"; then
    continue
  fi

  if [[ ! -f "$file" ]]; then
    continue
  fi

  checked=$((checked + 1))
  current_lines="$(wc -l < "$file" | trim_space)"
  previous_lines=0

  if [[ -n "$BASE_REF" ]] && git cat-file -e "${BASE_REF}:${file}" 2>/dev/null; then
    previous_lines="$(git show "${BASE_REF}:${file}" | wc -l | trim_space)"
  fi

  if (( current_lines <= MAX_LINES )); then
    echo "[file-size-guard] OK: ${file} (${current_lines} lines)"
    continue
  fi

  exception_limit=""
  if exception_limit="$(get_exception_limit "$file")"; then
    if (( current_lines <= exception_limit )); then
      echo "[file-size-guard] EXCEPTION: ${file} (${current_lines} lines, allowed up to ${exception_limit})"
      continue
    fi
    violations+=("${file}: ${current_lines} lines exceeds exception_limit=${exception_limit}")
    continue
  fi

  if (( previous_lines > MAX_LINES )); then
    allowed_lines=$((previous_lines + MAX_INCREASE))
    if (( current_lines <= allowed_lines )); then
      echo "[file-size-guard] LEGACY: ${file} (${previous_lines} -> ${current_lines}, over limit but within delta)"
      continue
    fi

    violations+=("${file}: ${previous_lines} -> ${current_lines} lines (limit=${MAX_LINES}, allowed growth=${MAX_INCREASE})")
    continue
  fi

  violations+=("${file}: ${current_lines} lines exceeds limit=${MAX_LINES} (previous=${previous_lines})")
done

if [[ $checked -eq 0 ]]; then
  echo "[file-size-guard] Нет целевых измененных файлов"
  exit 0
fi

if [[ "${#violations[@]}" -gt 0 ]]; then
  echo "[file-size-guard] FAIL: найдены нарушения лимита размера файлов"
  for violation in "${violations[@]}"; do
    echo "  - ${violation}"
  done
  exit 1
fi

echo "[file-size-guard] PASS: проверено файлов ${checked}"
