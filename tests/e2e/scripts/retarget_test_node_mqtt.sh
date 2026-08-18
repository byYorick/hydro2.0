#!/usr/bin/env bash
# Переключение MQTT-брокера физической test_node (dev :1883 ↔ e2e :1884)
# без setup-портала. Firmware принимает лёгкий payload БЕЗ channels[]:
#   {"mqtt":{"host":"<lan-ip>","port":1884}}
# Полный NodeConfig с docker DNS (mosquitto/localhost) не публикуем —
# config_callback игнорирует retarget, если в JSON есть channels[].
# Топик зональный: hydro/{gh}/{zone}/nd-test-irrig-1/config
# (никогда не hydro/system/).
#
# Usage:
#   tests/e2e/scripts/retarget_test_node_mqtt.sh --e2e
#   tests/e2e/scripts/retarget_test_node_mqtt.sh --dev
#   tests/e2e/scripts/retarget_test_node_mqtt.sh --host 192.168.3.2 --port 1884
#   tests/e2e/scripts/retarget_test_node_mqtt.sh --e2e --from-port 1883
#
# Env: TEST_NODE_GH_UID TEST_NODE_ZONE_UID TEST_NODE_UID MQTT_EXTERNAL_HOST

set -euo pipefail

usage() {
  cat <<'EOF'
Переключение MQTT брокера test_node (лёгкий payload без channels[]).

Использование:
  retarget_test_node_mqtt.sh --e2e
  retarget_test_node_mqtt.sh --dev
  retarget_test_node_mqtt.sh --host <IP> --port <N>

Режимы:
  --e2e              цель: порт 1884 (e2e compose, published на хост)
  --dev              цель: порт 1883 (dev compose)
  --host IP          host, который должна видеть нода (LAN IP хоста)
  --port N           порт брокера для ноды

Опции:
  --from-port N      текущий брокер ноды (куда слать config); иначе пробуем 1883 и 1884
  --broker-host H    куда слать mosquitto_pub (по умолчанию 127.0.0.1)
  --wait             ждать heartbeat на новом брокере
  --wait-sec N       таймаут ожидания heartbeat, сек (по умолчанию 45)
  -h, --help         эта справка

Переменные:
  TEST_NODE_GH_UID / TEST_NODE_ZONE_UID / TEST_NODE_UID
                     топик (по умолчанию gh-test-1 / zn-test-1 / nd-test-irrig-1)
  MQTT_EXTERNAL_HOST host для ноды, если не задан --host
                     (mosquitto / localhost / host.docker.internal — отбрасываются)

Примеры:
  tests/e2e/scripts/retarget_test_node_mqtt.sh --e2e
  tests/e2e/scripts/retarget_test_node_mqtt.sh --dev
  tests/e2e/scripts/retarget_test_node_mqtt.sh --host 192.168.3.2 --port 1884 --from-port 1883
EOF
}

MODE=""
NODE_HOST=""
TARGET_PORT=""
BROKER_HOST="${MQTT_BROKER_HOST:-127.0.0.1}"
FROM_PORT=""
WAIT_HEARTBEAT=0
WAIT_SEC=45
# Лабораторный fallback: типичный LAN IP хоста (не docker DNS).
LAB_DEFAULT_HOST="192.168.3.2"

is_unusable_node_host() {
  local host="${1:-}"
  case "${host}" in
    ""|mosquitto|localhost|127.0.0.1|127.*|::1|host.docker.internal)
      return 0
      ;;
  esac
  return 1
}

detect_lan_host() {
  local src=""
  src="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
  if [ -n "${src}" ] && ! is_unusable_node_host "${src}"; then
    printf '%s\n' "${src}"
    return 0
  fi
  return 1
}

resolve_node_host() {
  local candidate="${1:-}"
  if [ -n "${candidate}" ]; then
    if is_unusable_node_host "${candidate}"; then
      echo "Ошибка: host '${candidate}' нода на LAN не сможет резолвить. Укажите LAN IP хоста (например ${LAB_DEFAULT_HOST})." >&2
      exit 1
    fi
    printf '%s\n' "${candidate}"
    return 0
  fi

  candidate="${MQTT_EXTERNAL_HOST:-}"
  if [ -n "${candidate}" ] && ! is_unusable_node_host "${candidate}"; then
    echo "Host для ноды из MQTT_EXTERNAL_HOST: ${candidate}" >&2
    printf '%s\n' "${candidate}"
    return 0
  fi
  if [ -n "${candidate}" ]; then
    echo "MQTT_EXTERNAL_HOST='${candidate}' непригоден для ESP32 на LAN (docker DNS / loopback), пропускаю." >&2
  fi

  if candidate="$(detect_lan_host)"; then
    echo "Host для ноды определён по LAN-маршруту: ${candidate}" >&2
    printf '%s\n' "${candidate}"
    return 0
  fi

  echo "Не удалось определить LAN IP, использую лабораторный default ${LAB_DEFAULT_HOST}" >&2
  printf '%s\n' "${LAB_DEFAULT_HOST}"
}

is_port() {
  local port="${1:-}"
  [[ "${port}" =~ ^[0-9]+$ ]] && [ "${port}" -ge 1 ] && [ "${port}" -le 65535 ]
}

require_mosquitto_pub() {
  if ! command -v mosquitto_pub >/dev/null 2>&1; then
    echo "Ошибка: нужен mosquitto_pub в PATH" >&2
    exit 1
  fi
}

has_mosquitto_sub() {
  command -v mosquitto_sub >/dev/null 2>&1
}

probe_heartbeat() {
  local port="$1"
  local wait_sec="${2:-2}"
  local topic="$3"
  if ! has_mosquitto_sub; then
    return 1
  fi
  mosquitto_sub -h "${BROKER_HOST}" -p "${port}" -t "${topic}" -C 1 -W "${wait_sec}" >/dev/null 2>&1
}

publish_payload() {
  local port="$1"
  local topic="$2"
  local payload="$3"
  printf '%s' "${payload}" | mosquitto_pub -h "${BROKER_HOST}" -p "${port}" -q 1 -t "${topic}" -s
}

while [ $# -gt 0 ]; do
  case "$1" in
    --e2e)
      if [ -n "${MODE}" ] && [ "${MODE}" != "e2e" ]; then
        echo "Ошибка: укажите только один режим (--e2e, --dev или --host/--port)." >&2
        exit 1
      fi
      MODE="e2e"
      shift
      ;;
    --dev)
      if [ -n "${MODE}" ] && [ "${MODE}" != "dev" ]; then
        echo "Ошибка: укажите только один режим (--e2e, --dev или --host/--port)." >&2
        exit 1
      fi
      MODE="dev"
      shift
      ;;
    --host)
      NODE_HOST="${2:-}"
      if [ -z "${NODE_HOST}" ]; then
        echo "Ошибка: --host требует IP." >&2
        exit 1
      fi
      shift 2
      ;;
    --port)
      TARGET_PORT="${2:-}"
      if [ -z "${TARGET_PORT}" ]; then
        echo "Ошибка: --port требует номер порта." >&2
        exit 1
      fi
      shift 2
      ;;
    --from-port|--broker-port)
      FROM_PORT="${2:-}"
      if [ -z "${FROM_PORT}" ]; then
        echo "Ошибка: --from-port требует номер порта." >&2
        exit 1
      fi
      shift 2
      ;;
    --broker-host)
      BROKER_HOST="${2:-}"
      if [ -z "${BROKER_HOST}" ]; then
        echo "Ошибка: --broker-host требует хост." >&2
        exit 1
      fi
      shift 2
      ;;
    --wait)
      WAIT_HEARTBEAT=1
      shift
      ;;
    --wait-sec)
      WAIT_SEC="${2:-}"
      if [ -z "${WAIT_SEC}" ]; then
        echo "Ошибка: --wait-sec требует число секунд." >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ -z "${MODE}" ] && { [ -z "${NODE_HOST}" ] || [ -z "${TARGET_PORT}" ]; }; then
  echo "Ошибка: нужен --e2e, --dev или пара --host IP --port N." >&2
  usage >&2
  exit 1
fi

if [ -z "${TARGET_PORT}" ]; then
  case "${MODE}" in
    e2e) TARGET_PORT=1884 ;;
    dev) TARGET_PORT=1883 ;;
  esac
fi

if ! is_port "${TARGET_PORT}"; then
  echo "Ошибка: некорректный порт цели '${TARGET_PORT}'." >&2
  exit 1
fi

if [ -n "${FROM_PORT}" ] && ! is_port "${FROM_PORT}"; then
  echo "Ошибка: некорректный --from-port '${FROM_PORT}'." >&2
  exit 1
fi

if ! [[ "${WAIT_SEC}" =~ ^[0-9]+$ ]] || [ "${WAIT_SEC}" -lt 1 ]; then
  echo "Ошибка: --wait-sec должен быть положительным числом." >&2
  exit 1
fi

GH="${TEST_NODE_GH_UID:-gh-test-1}"
ZONE="${TEST_NODE_ZONE_UID:-zn-test-1}"
NODE_UID="${TEST_NODE_UID:-nd-test-irrig-1}"
if [ "${NODE_UID}" = "auto" ] || [ -z "${NODE_UID}" ]; then
  NODE_UID="nd-test-irrig-1"
fi

if [ "${GH}" = "system" ]; then
  echo "Ошибка: не публикуем в hydro/system/. Задайте TEST_NODE_GH_UID (например gh-test-1)." >&2
  exit 1
fi

TOPIC="hydro/${GH}/${ZONE}/${NODE_UID}/config"
HEARTBEAT_TOPIC="hydro/${GH}/${ZONE}/${NODE_UID}/heartbeat"

case "${TOPIC}" in
  hydro/system/*)
    echo "Ошибка: топик '${TOPIC}' попадает в hydro/system/ — retarget только в зональный namespace." >&2
    exit 1
    ;;
esac

NODE_HOST="$(resolve_node_host "${NODE_HOST}")"
if [[ "${NODE_HOST}" == *$'\n'* ]] || [[ "${NODE_HOST}" == *"\""* ]]; then
  echo "Ошибка: host содержит недопустимые символы." >&2
  exit 1
fi

# Payload ТОЛЬКО mqtt.host + mqtt.port, без channels[] и без docker DNS.
PAYLOAD="$(printf '{"mqtt":{"host":"%s","port":%s}}' "${NODE_HOST}" "${TARGET_PORT}")"

require_mosquitto_pub
if [ "${WAIT_HEARTBEAT}" -eq 1 ] && ! has_mosquitto_sub; then
  echo "Ошибка: --wait требует mosquitto_sub в PATH" >&2
  exit 1
fi

echo "Цель для ноды: ${NODE_HOST}:${TARGET_PORT}"
echo "Топик: ${TOPIC}"
echo "Payload: ${PAYLOAD}"

FROM_PORTS=()
if [ -n "${FROM_PORT}" ]; then
  FROM_PORTS=("${FROM_PORT}")
  echo "Текущий брокер задан явно: ${BROKER_HOST}:${FROM_PORT}"
else
  DETECTED=""
  if has_mosquitto_sub; then
    echo "Ищу heartbeat ноды на текущем брокере (${BROKER_HOST}:1883 и :1884)..."
    if probe_heartbeat 1883 2 "${HEARTBEAT_TOPIC}"; then
      DETECTED=1883
      echo "Нода сейчас на ${BROKER_HOST}:1883 (dev)."
    elif probe_heartbeat 1884 2 "${HEARTBEAT_TOPIC}"; then
      DETECTED=1884
      echo "Нода сейчас на ${BROKER_HOST}:1884 (e2e)."
    fi
  fi
  if [ -n "${DETECTED}" ]; then
    FROM_PORTS=("${DETECTED}")
  else
    FROM_PORTS=(1883 1884)
    echo "Heartbeat не найден. Публикую на оба брокера (${BROKER_HOST}:1883 и :1884)."
  fi
fi

published=0
for try_port in "${FROM_PORTS[@]}"; do
  echo "Публикую config на ${BROKER_HOST}:${try_port} ..."
  if publish_payload "${try_port}" "${TOPIC}" "${PAYLOAD}"; then
    published=1
    echo "Опубликовано на ${BROKER_HOST}:${try_port}."
  else
    echo "Не удалось опубликовать на ${BROKER_HOST}:${try_port}." >&2
  fi
done

if [ "${published}" -ne 1 ]; then
  echo "Ошибка: не удалось опубликовать ни на одном текущем брокере." >&2
  echo "Проверьте, что брокер запущен и порты 1883/1884 проброшены на хост." >&2
  exit 1
fi

echo "Config отправлен. Нода должна сохранить MQTT в NVS и перезагрузиться."

if [ "${WAIT_HEARTBEAT}" -eq 1 ]; then
  echo "Жду heartbeat на новом брокере ${BROKER_HOST}:${TARGET_PORT} (до ${WAIT_SEC} с)..."
  if probe_heartbeat "${TARGET_PORT}" "${WAIT_SEC}" "${HEARTBEAT_TOPIC}"; then
    echo "Готово: heartbeat получен на ${BROKER_HOST}:${TARGET_PORT}."
  else
    echo "Ошибка: heartbeat на ${BROKER_HOST}:${TARGET_PORT} не появился за ${WAIT_SEC} с." >&2
    echo "Проверьте UART и что нода видит ${NODE_HOST}:${TARGET_PORT}." >&2
    exit 1
  fi
else
  echo "Проверка heartbeat пропущена (добавьте --wait, чтобы дождаться нового брокера)."
fi
