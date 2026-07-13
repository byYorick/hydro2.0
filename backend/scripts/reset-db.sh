#!/usr/bin/env bash
# Полный reset hydro_dev: schema + Redis + MQTT retained + рестарт runtime-сервисов.
# Вызывается из корневого `make reset-db`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"
COMPOSE_FILE="${BACKEND_COMPOSE_FILE:-${BACKEND_DIR}/docker-compose.dev.yml}"

if command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker-compose}"
else
  DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker compose}"
fi

compose() {
  # shellcheck disable=SC2086
  ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" "$@"
}

RESET_DB_DATABASE="${RESET_DB_DATABASE:-hydro_dev}"
RESET_DB_APP_ENV="${RESET_DB_APP_ENV:-local}"
RESET_DB_SEEDER_CLASS="${RESET_DB_SEEDER_CLASS:-ResetDbSeeder}"
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"

cd "${PROJECT_ROOT}"

echo "==> reset-db: target DB=${RESET_DB_DATABASE} seeder=${RESET_DB_SEEDER_CLASS}"

echo "==> 1/5 PostgreSQL: drop public schema (hypertables/partitions) + extensions"
# DROP SCHEMA public CASCADE надёжнее migrate:fresh на Timescale (как tests/RefreshDatabase.php).
# timescaledb установлен в schema public — CASCADE снимает extension, ниже создаём заново.
compose exec -T db psql -U hydro -d "${RESET_DB_DATABASE}" -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO CURRENT_USER;
GRANT ALL ON SCHEMA public TO PUBLIC;
GRANT ALL ON SCHEMA public TO hydro;
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- pg_cron разрешён только в cron.database_name (обычно hydro_dev)
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS pg_cron;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'pg_cron skipped: %', SQLERRM;
END
$$;
SQL

echo "==> 2/5 Laravel: migrate + seed"
compose exec -T \
  -e "APP_ENV=${RESET_DB_APP_ENV}" \
  -e "DB_DATABASE=${RESET_DB_DATABASE}" \
  laravel php artisan migrate --force --no-interaction
compose exec -T \
  -e "APP_ENV=${RESET_DB_APP_ENV}" \
  -e "DB_DATABASE=${RESET_DB_DATABASE}" \
  laravel php artisan db:seed --class="${RESET_DB_SEEDER_CLASS}" --force --no-interaction

echo "==> 3/5 Redis: FLUSHALL"
compose exec -T redis redis-cli FLUSHALL >/dev/null

echo "==> 4/5 MQTT: stop node-sim publishers, clear retained hydro/#, restart broker"
# node-sim публикует retained status/LWT — иначе сразу после flush снова появятся «призраки».
compose stop node-sim-manager >/dev/null 2>&1 || true
if command -v mosquitto_sub >/dev/null 2>&1 && command -v mosquitto_pub >/dev/null 2>&1; then
  mapfile -t RETAINED_TOPICS < <(
    timeout 3 mosquitto_sub -h "${MQTT_HOST}" -p "${MQTT_PORT}" -t 'hydro/#' -v --retained-only 2>/dev/null \
      | awk '{print $1}' \
      | sort -u \
      || true
  )
  cleared=0
  for topic in "${RETAINED_TOPICS[@]:-}"; do
    [[ -z "${topic}" ]] && continue
    if mosquitto_pub -h "${MQTT_HOST}" -p "${MQTT_PORT}" -t "${topic}" -n -r; then
      cleared=$((cleared + 1))
    fi
  done
  echo "    cleared ${cleared} retained topic(s)"
else
  echo "    mosquitto_sub/pub недоступны на хосте — полагаемся на restart mqtt"
fi
compose restart mqtt >/dev/null

echo "==> 5/5 Restart runtime services (node-sim-manager остаётся остановленным)"
compose restart \
  laravel \
  automation-engine \
  history-logger \
  mqtt-bridge \
  telemetry-aggregator \
  >/dev/null

echo "==> reset-db: done (DB=${RESET_DB_DATABASE}, Redis flushed, MQTT retained cleared, services restarted)"
echo "    node-sim-manager остановлен; при необходимости: ${DOCKER_COMPOSE} -f ${COMPOSE_FILE} start node-sim-manager"
