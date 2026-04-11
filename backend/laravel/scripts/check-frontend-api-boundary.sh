#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_DIR="resources/js"

if command -v rg >/dev/null 2>&1; then
  SEARCH_TOOL="rg"
else
  SEARCH_TOOL="grep"
fi

# Запрещаем прямые внутренние сервисные адреса и порты в UI-коде.
# Фронтенд должен ходить к backend через относительные пути Laravel API (/api/*).
PATTERN_INTERNAL_HOSTS='(https?|wss?)://(history-logger|automation-engine|mqtt-bridge|scheduler|db|redis|mqtt|laravel|node-sim-manager)(:[0-9]+)?(/|$)'
PATTERN_INTERNAL_LOCAL_PORTS='(https?|wss?)://(localhost|127\.0\.0\.1|0\.0\.0\.0):(9300|9405|9000|5432|6379|1883|9100)(/|$)'
PATTERN_INTERNAL_HOSTPORT='(history-logger:9300|automation-engine:9405|mqtt-bridge:9000|db:5432|redis:6379|mqtt:1883|node-sim-manager:9100)([^0-9]|$)'

search_pattern() {
  local pattern="$1"
  if [[ "$SEARCH_TOOL" == "rg" ]]; then
    rg --pcre2 -n -e "$pattern" "$TARGET_DIR" \
      --glob '!**/__tests__/**' \
      --glob '!**/*.{spec,test}.{js,ts,tsx,vue}'
  else
    grep -RInE "$pattern" "$TARGET_DIR" \
      --include='*.js' \
      --include='*.ts' \
      --include='*.tsx' \
      --include='*.vue' \
      --exclude-dir='__tests__' \
      --exclude='*.spec.js' \
      --exclude='*.spec.ts' \
      --exclude='*.spec.tsx' \
      --exclude='*.spec.vue' \
      --exclude='*.test.js' \
      --exclude='*.test.ts' \
      --exclude='*.test.tsx' \
      --exclude='*.test.vue'
  fi
}

set +e
MATCHES_HOSTS="$(search_pattern "$PATTERN_INTERNAL_HOSTS")"
STATUS_HOSTS=$?
MATCHES_LOCAL_PORTS="$(search_pattern "$PATTERN_INTERNAL_LOCAL_PORTS")"
STATUS_LOCAL_PORTS=$?
MATCHES_HOSTPORT="$(search_pattern "$PATTERN_INTERNAL_HOSTPORT")"
STATUS_HOSTPORT=$?
set -e

if [[ $STATUS_HOSTS -eq 0 || $STATUS_LOCAL_PORTS -eq 0 || $STATUS_HOSTPORT -eq 0 ]]; then
  echo "ERROR: direct internal service endpoints detected in frontend sources."
  echo "Use Laravel API endpoints (e.g. /api/system/health) instead of internal hostnames/ports."
  [[ -n "$MATCHES_HOSTS" ]] && echo "$MATCHES_HOSTS"
  [[ -n "$MATCHES_LOCAL_PORTS" ]] && echo "$MATCHES_LOCAL_PORTS"
  [[ -n "$MATCHES_HOSTPORT" ]] && echo "$MATCHES_HOSTPORT"
  exit 1
fi

# Фаза 3: строгая граница apiClient.
# `@/utils/apiClient` разрешено импортировать ТОЛЬКО из двух мест:
#   1. resources/js/services/api/_client.ts  — новый типизированный слой
#   2. resources/js/composables/useApi.ts    — legacy бридж, уходит по мере миграции
# Это жёсткая инвариантность: если появится третий импортёр — падаем.
ALLOWED_API_CLIENT_IMPORTERS=(
  "resources/js/services/api/_client.ts"
  "resources/js/composables/useApi.ts"
)
API_CLIENT_PATTERN="from ['\"]@/utils/apiClient['\"]"

set +e
if [[ "$SEARCH_TOOL" == "rg" ]]; then
  API_CLIENT_IMPORTS="$(rg -l "$API_CLIENT_PATTERN" "$TARGET_DIR" \
    --glob '!**/__tests__/**' \
    --glob '!**/*.{spec,test}.{js,ts,tsx,vue}' \
    || true)"
else
  API_CLIENT_IMPORTS="$(grep -RIlE "$API_CLIENT_PATTERN" "$TARGET_DIR" \
    --include='*.ts' --include='*.tsx' --include='*.vue' --include='*.js' \
    --exclude-dir='__tests__' 2>/dev/null || true)"
fi
set -e

UNAUTHORIZED_IMPORTERS=""
if [[ -n "$API_CLIENT_IMPORTS" ]]; then
  while IFS= read -r importer; do
    [[ -z "$importer" ]] && continue
    authorized=false
    for allowed in "${ALLOWED_API_CLIENT_IMPORTERS[@]}"; do
      if [[ "$importer" == *"$allowed" ]]; then
        authorized=true
        break
      fi
    done
    if [[ "$authorized" == false ]]; then
      UNAUTHORIZED_IMPORTERS+="$importer"$'\n'
    fi
  done <<< "$API_CLIENT_IMPORTS"
fi

if [[ -n "$UNAUTHORIZED_IMPORTERS" ]]; then
  echo "ERROR: unauthorized import of @/utils/apiClient detected."
  echo "Only services/api/_client.ts and composables/useApi.ts are allowed to import it directly."
  echo "Other code must use: import { api } from '@/services/api'"
  echo
  echo "Offenders:"
  echo "$UNAUTHORIZED_IMPORTERS"
  exit 1
fi

echo "OK: frontend API boundary check passed."
