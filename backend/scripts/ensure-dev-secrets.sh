#!/usr/bin/env bash
# Генерирует сервисные секреты в env-файл, если их нет или там остались
# скомпрометированные значения из репозитория.
#
# Все Bearer-токены сервисов получают одно значение, чтобы цепочка
# Laravel -> automation-engine -> history-logger не разъехалась.
#
#   bash backend/scripts/ensure-dev-secrets.sh backend/.env
#   bash backend/scripts/ensure-dev-secrets.sh tests/e2e/.env
#
# Файл можно подключить через source: тогда выполнятся только функции.

ensure_dev_secrets() {
  local env_file="${1:-}"
  if [[ -z "$env_file" ]]; then
    echo "usage: ensure_dev_secrets <env-file>" >&2
    return 2
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "ensure-dev-secrets: openssl is required to generate secrets" >&2
    return 1
  fi

  umask 077
  mkdir -p "$(dirname "$env_file")"
  if [[ ! -f "$env_file" ]]; then
    : > "$env_file"
  fi
  chmod 600 "$env_file"

  local -a service_keys=(
    PY_API_TOKEN
    PY_INGEST_TOKEN
    LARAVEL_API_TOKEN
    HISTORY_LOGGER_API_TOKEN
    AUTOMATION_LARAVEL_SCHEDULER_API_TOKEN
    DIGITAL_TWIN_API_TOKEN
    NODE_SIM_MANAGER_TOKEN
  )

  # Один Bearer на всю цепочку. Берём уже заданное хорошее значение
  # (не только PY_API_TOKEN): иначе пустой PY_API_TOKEN затирается новым
  # токеном, а заранее заданный HISTORY_LOGGER_API_TOKEN остаётся другим.
  local shared="" current key
  for key in "${service_keys[@]}"; do
    current="$(_dev_secret_get "$env_file" "$key")"
    if _dev_secret_is_bad_token "$current"; then
      continue
    fi
    if [[ -z "$shared" ]]; then
      shared="$current"
    elif [[ "$shared" != "$current" ]]; then
      echo "ensure-dev-secrets: warning: ${key} отличается от общего Bearer, значение не перезаписано" >&2
    fi
  done
  if [[ -z "$shared" ]]; then
    shared="$(_dev_secret_generate_token)"
    echo "ensure-dev-secrets: общий Bearer сгенерирован (пустые или скомпрометированные токены заменены)" >&2
  fi

  for key in "${service_keys[@]}"; do
    current="$(_dev_secret_get "$env_file" "$key")"
    if _dev_secret_is_bad_token "$current"; then
      _dev_secret_set "$env_file" "$key" "$shared"
    fi
  done

  current="$(_dev_secret_get "$env_file" ALERTMANAGER_WEBHOOK_SECRET)"
  if _dev_secret_is_bad_webhook "$current"; then
    _dev_secret_set "$env_file" ALERTMANAGER_WEBHOOK_SECRET "$(_dev_secret_generate_token)"
    echo "ensure-dev-secrets: ALERTMANAGER_WEBHOOK_SECRET сгенерирован" >&2
  fi

  current="$(_dev_secret_get "$env_file" APP_KEY)"
  if _dev_secret_is_bad_app_key "$current"; then
    _dev_secret_set "$env_file" APP_KEY "$(_dev_secret_generate_app_key)"
    echo "ensure-dev-secrets: APP_KEY сгенерирован" >&2
  fi

  local mqtt_key
  for mqtt_key in MQTT_PYTHON_SERVICE_PASS MQTT_AUTOMATION_ENGINE_PASS MQTT_HISTORY_LOGGER_PASS MQTT_MQTT_BRIDGE_PASS MQTT_ESP32_NODE_PASS; do
    current="$(_dev_secret_get "$env_file" "$mqtt_key")"
    if _dev_secret_is_bad_mqtt_pass "$current"; then
      _dev_secret_set "$env_file" "$mqtt_key" "$(_dev_secret_generate_token)"
      echo "ensure-dev-secrets: ${mqtt_key} сгенерирован" >&2
    fi
  done

  current="$(_dev_secret_get "$env_file" NODE_SECRET_WRAP_PASSPHRASE)"
  if _dev_secret_is_bad_mqtt_pass "$current"; then
    _dev_secret_set "$env_file" NODE_SECRET_WRAP_PASSPHRASE "$(_dev_secret_get "$env_file" MQTT_ESP32_NODE_PASS)"
    echo "ensure-dev-secrets: NODE_SECRET_WRAP_PASSPHRASE совпадает с MQTT_ESP32_NODE_PASS" >&2
  fi

  current="$(_dev_secret_get "$env_file" GRAFANA_ADMIN_PASSWORD)"
  if _dev_secret_is_bad_grafana_password "$current"; then
    _dev_secret_set "$env_file" GRAFANA_ADMIN_PASSWORD "$(_dev_secret_generate_token)"
    echo "ensure-dev-secrets: GRAFANA_ADMIN_PASSWORD сгенерирован" >&2
  fi

  current="$(_dev_secret_get "$env_file" HISTORY_LOGGER_AE_TOKEN)"
  local general_hl
  general_hl="$(_dev_secret_get "$env_file" HISTORY_LOGGER_API_TOKEN)"
  if [[ -z "$general_hl" ]]; then
    general_hl="$(_dev_secret_get "$env_file" PY_INGEST_TOKEN)"
  fi
  if _dev_secret_is_bad_token "$current" || [[ -n "$general_hl" && "$current" == "$general_hl" ]] || [[ -n "$shared" && "$current" == "$shared" ]]; then
    local ae_token
    ae_token="$(_dev_secret_generate_token)"
    while [[ "$ae_token" == "$general_hl" || "$ae_token" == "$shared" ]]; do
      ae_token="$(_dev_secret_generate_token)"
    done
    _dev_secret_set "$env_file" HISTORY_LOGGER_AE_TOKEN "$ae_token"
    echo "ensure-dev-secrets: HISTORY_LOGGER_AE_TOKEN сгенерирован отдельно от общего Bearer" >&2
  fi
}

load_env_defaults() {
  local env_file="${1:-}"
  local line key value
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
}

_dev_secret_is_bad_token() {
  case "${1:-}" in
    ''|dev-token-12345|test-token-12345) return 0 ;;
    *) return 1 ;;
  esac
}

_dev_secret_is_bad_mqtt_pass() {
  case "${1:-}" in
    ''|esp32_pass|logger_pass|bridge_pass|automation_pass|python_service_pass) return 0 ;;
    *) return 1 ;;
  esac
}

_dev_secret_is_bad_grafana_password() {
  case "${1:-}" in
    ''|admin) return 0 ;;
    *) return 1 ;;
  esac
}

_dev_secret_is_bad_webhook() {
  case "${1:-}" in
    ''|dev-alertmanager-webhook-secret) return 0 ;;
    *) return 1 ;;
  esac
}

_dev_secret_is_bad_app_key() {
  case "${1:-}" in
    ''|'base64:Go+le0yjTxoJWvbMib0hJTWXbzUdG00oeQpEVdNwUyc=') return 0 ;;
    *) return 1 ;;
  esac
}

_dev_secret_generate_token() {
  openssl rand -hex 32
}

_dev_secret_generate_app_key() {
  printf 'base64:%s' "$(openssl rand -base64 32 | tr -d '\n')"
}

_dev_secret_get() {
  local env_file="$1"
  local key="$2"
  local line
  line="$(grep -E "^${key}=" "$env_file" 2>/dev/null | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' ""
    return 0
  fi
  printf '%s' "${line#*=}"
}

_dev_secret_set() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  local tmp
  tmp="$(mktemp)"
  grep -vE "^${key}=" "$env_file" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$env_file"
  chmod 600 "$env_file"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  if [[ $# -lt 1 ]]; then
    echo "usage: ensure-dev-secrets.sh <env-file>" >&2
    exit 2
  fi
  ensure_dev_secrets "$1"
fi
