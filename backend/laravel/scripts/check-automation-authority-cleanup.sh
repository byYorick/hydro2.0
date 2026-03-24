#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -d "$PROJECT_ROOT/app" && -d "$PROJECT_ROOT/routes" ]]; then
  PHP_APP_DIR="$PROJECT_ROOT/app"
  ROUTES_DIR="$PROJECT_ROOT/routes"
  JS_DIR="$PROJECT_ROOT/resources/js"
  PYTHON_DIR="$PROJECT_ROOT/../services/automation-engine"
else
  REPO_DIR="$(cd "$PROJECT_ROOT/../.." && pwd)"
  PHP_APP_DIR="$REPO_DIR/backend/laravel/app"
  ROUTES_DIR="$REPO_DIR/backend/laravel/routes"
  JS_DIR="$REPO_DIR/backend/laravel/resources/js"
  PYTHON_DIR="$REPO_DIR/backend/services/automation-engine"
fi

CODE_TARGETS=("$PHP_APP_DIR" "$ROUTES_DIR")
if [[ -d "$PYTHON_DIR" ]]; then
  CODE_TARGETS+=("$PYTHON_DIR")
fi

if command -v rg >/dev/null 2>&1; then
  SEARCH_TOOL="rg"
else
  SEARCH_TOOL="grep"
fi

search_code() {
  local pattern="$1"
  shift
  if [[ "$SEARCH_TOOL" == "rg" ]]; then
    rg -n --pcre2 "$pattern" "$@" \
      --glob '!**/vendor/**' \
      --glob '!**/node_modules/**' \
      --glob '!**/database/migrations/**' \
      --glob '!**/database/seeders/**' \
      --glob '!**/tests/**' \
      --glob '!**/docs/**' \
      --glob '!**/doc_ai/**' \
      --glob '!**/*.svg' \
      --glob '!**/*.mmd'
  else
    grep -RInE "$pattern" "$@"
  fi
}

fail_if_found() {
  local label="$1"
  local pattern="$2"
  shift 2
  local matches=""
  local status=1

  set +e
  matches="$(search_code "$pattern" "$@")"
  status=$?
  set -e

  if [[ $status -eq 0 && -n "$matches" ]]; then
    echo "ERROR: ${label}"
    echo "$matches"
    exit 1
  fi
}

fail_if_found \
  "legacy automation services/models/classes detected in live code paths" \
  "\\b(ZonePidConfigService|ZoneAutomationLogicProfileService|ZoneCorrectionConfigService|ZonePidConfig|ZoneAutomationLogicProfile|ZoneCorrectionConfigVersion|GrowCycleOverride)\\b" \
  "${CODE_TARGETS[@]}"

fail_if_found \
  "legacy automation table access detected in runtime/business paths" \
  "(zone_pid_configs|zone_correction_configs|zone_correction_config_versions|zone_automation_logic_profiles|greenhouse_automation_logic_profiles|zone_process_calibrations|grow_cycle_overrides|automation_runtime_overrides|system_automation_settings)" \
  "${CODE_TARGETS[@]}"

fail_if_found \
  "env() usage detected in Laravel services/runtime logic" \
  "\\benv\\s*\\(" \
  "$PHP_APP_DIR/Services"

fail_if_found \
  "legacy frontend automation API/composable detected" \
  "(useZonePidConfig|useZoneAutomationLogicProfile|/api/.*/(pid-configs|automation-logic-profiles|correction-configs))" \
  "$JS_DIR"

echo "OK: automation authority cleanup guard passed."
