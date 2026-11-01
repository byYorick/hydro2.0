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

  local shared current key
  current="$(_dev_secret_get "$env_file" PY_API_TOKEN)"
  if _dev_secret_is_bad_token "$current"; then
    shared="$(_dev_secret_generate_token)"
    echo "ensure-dev-secrets: PY_API_TOKEN сгенерирован (пустое или скомпрометированное значение заменено)" >&2
  else
    shared="$current"
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
