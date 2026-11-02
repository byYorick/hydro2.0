#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
repo_dir=$PWD
env_file=$(mktemp)
source backend/scripts/ensure-dev-secrets.sh
ensure_dev_secrets "$env_file"
load_env_defaults "$env_file"
export COMPOSE_PROJECT_NAME=hydro-ci-pipeline
compose=(docker compose --env-file "$env_file" -f tests/e2e/docker-compose.e2e.yml)
cleanup() {
  "${compose[@]}" logs --no-color --tail=80 > /tmp/hydro-ci-pipeline.log 2>&1 || true
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$env_file"
}
trap cleanup EXIT
# e2e compose bind-mounts source over /app, so install its locked vendor first.
docker run --rm -v "$repo_dir/backend/laravel:/app" -w /app composer:2 \
  composer install --no-interaction --prefer-dist --no-scripts --ignore-platform-req=ext-pdo_pgsql
"${compose[@]}" up -d --build --wait --wait-timeout 240 laravel history-logger automation-engine mqtt-bridge
"${compose[@]}" exec -T laravel php artisan migrate --force
export CI_PIPELINE_API_TOKEN
CI_PIPELINE_API_TOKEN=$("${compose[@]}" exec -T laravel php artisan e2e:auth-bootstrap --email=ci-pipeline@example.com --role=admin)
export CI_LARAVEL_CONTAINER
CI_LARAVEL_CONTAINER=$("${compose[@]}" ps -q laravel)
network=$(docker inspect "$CI_LARAVEL_CONTAINER" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}')
docker build -t hydro-ci-pipeline-runner -f tests/e2e/Dockerfile.e2e-runner tests/e2e
docker run --rm --network "$network" \
  -v "$repo_dir:/repo" -v /var/run/docker.sock:/var/run/docker.sock \
  -e CI_PIPELINE_API_TOKEN -e CI_LARAVEL_CONTAINER -e PY_API_TOKEN \
  -e LARAVEL_URL=http://laravel -e AUTOMATION_ENGINE_HOST=automation-engine \
  -e AUTOMATION_ENGINE_API_PORT=9505 -e MQTT_HOST=mosquitto -e MQTT_PORT=1883 \
  -e DB_HOST=postgres -e DB_PORT=5432 -e DB_DATABASE=hydro_e2e -e DB_USERNAME=hydro -e DB_PASSWORD=hydro_e2e \
  -w /repo/tests/e2e hydro-ci-pipeline-runner sh -c \
  'python -m unittest discover -s tests -p test_mqtt_probe_buffer.py && python /repo/tools/ci/pipeline_smoke.py'
