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
PATTERN_INTERNAL_LOCAL_PORTS='(https?|wss?)://(localhost|127\.0\.0\.1|0\.0\.0\.0):(9300|9401|9000|9402|5432|6379|1883|9100)(/|$)'
PATTERN_INTERNAL_HOSTPORT='(history-logger:9300|automation-engine:9401|mqtt-bridge:9000|scheduler:9402|db:5432|redis:6379|mqtt:1883|node-sim-manager:9100)([^0-9]|$)'

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

echo "OK: frontend API boundary check passed."
