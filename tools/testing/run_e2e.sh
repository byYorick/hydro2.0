#!/bin/bash
# One-command E2E test runner
# Поднимает стенд → дожидается readiness → прогоняет сценарии → выводит отчёт

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
E2E_DIR="$PROJECT_ROOT/tests/e2e"
COMPOSE_FILE="$E2E_DIR/docker-compose.e2e.yml"
ENV_FILE="$E2E_DIR/.env.e2e"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функции
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка наличия docker-compose
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    log_error "docker-compose or docker not found. Please install Docker."
    exit 1
fi

DOCKER_COMPOSE_CMD="docker-compose"
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
fi

# Переход в директорию E2E
cd "$E2E_DIR"

# .env.e2e (опционально): если есть - подхватываем, если нет - работаем на дефолтах
if [ ! -f "$ENV_FILE" ]; then
    log_warn ".env.e2e not found, using defaults (you can create tests/e2e/.env.e2e to override)"
fi

# Загрузка переменных окружения
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Функция ожидания health=healthy у сервиса в docker compose
wait_healthy() {
    local service="$1"
    local max_attempts="${2:-60}"
    local attempt=0

    log_info "Waiting for $service to be healthy..."

    while [ $attempt -lt $max_attempts ]; do
        # получаем container id для сервиса
        local cid
        cid="$($DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)"
        if [ -n "$cid" ]; then
            local health
            health="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")"
            if [ "$health" = "healthy" ] || [ "$health" = "none" ]; then
                log_info "$service is healthy ✓"
                return 0
            fi
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_error "$service is not healthy after $((max_attempts * 2)) seconds"
    return 1
}

# Функция проверки health endpoint
check_health() {
    local service=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=0
    
    log_info "Checking health of $service..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            log_info "$service health check passed ✓"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    log_error "$service health check failed after $((max_attempts * 2)) seconds"
    return 1
}

# Шаг 1: Поднять docker-compose
log_info "Step 1: Starting E2E test environment..."
set +e
UP_OUTPUT="$($DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d --build 2>&1)"
UP_EXIT=$?
set -e
if [ $UP_EXIT -ne 0 ]; then
    echo "$UP_OUTPUT"
    if echo "$UP_OUTPUT" | grep -q "all predefined address pools have been fully subnetted"; then
        log_warn "Docker network pool exhausted. Running 'docker network prune -f' and retrying once..."
        docker network prune -f
        $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d --build
    else
        log_error "docker compose up failed"
        exit $UP_EXIT
    fi
fi

# Шаг 2: Дождаться readiness всех сервисов
log_info "Step 2: Waiting for services to be ready..."

wait_healthy "postgres" 60 || { $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs postgres; exit 1; }
wait_healthy "redis" 60 || { $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs redis; exit 1; }
wait_healthy "mosquitto" 60 || { $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs mosquitto; exit 1; }

# Проверка Laravel
LARAVEL_URL="http://localhost:${LARAVEL_PORT:-8081}"
if ! check_health "Laravel" "$LARAVEL_URL/api/system/health" 60; then
    log_error "Laravel failed to start"
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs laravel
    exit 1
fi

# Детерминированная подготовка БД для E2E
log_info "Running Laravel migrations + E2E seeders..."
$DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" exec -T laravel php artisan migrate --force
$DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" exec -T laravel php artisan db:seed --class=E2eUserSeeder --force
$DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" exec -T laravel php artisan db:seed --class=E2eDataSeeder --force
log_info "Laravel migrations + E2E seeders completed ✓"

# Проверка History Logger
HISTORY_LOGGER_URL="http://localhost:${HISTORY_LOGGER_PORT:-9302}"
if ! check_health "History Logger" "$HISTORY_LOGGER_URL/health" 30; then
    log_error "History Logger failed to start"
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs history-logger
    exit 1
fi

# Проверка node-sim
log_info "Checking node-sim connection..."
sleep 5  # Даём время на подключение
if $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs node-sim | grep -q "Connected to MQTT\|connected to MQTT"; then
    log_info "node-sim connected to MQTT ✓"
else
    log_warn "node-sim MQTT connection check skipped (may need more time)"
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" logs node-sim | tail -20
fi

# Шаг 3: Запустить E2E сценарии
log_info "Step 3: Running E2E scenarios..."

# Создать директорию для отчётов
mkdir -p "$E2E_DIR/reports"

# Сценарии для запуска
SCENARIOS=(
    "E01_bootstrap"
    "E02_command_happy"
    "E04_error_alert"
    "E05_unassigned_attach"
    "E07_ws_reconnect_snapshot_replay"
)

# Результаты
PASSED=0
FAILED=0
FAILED_SCENARIOS=()

# Экспорт переменных для E2E runner
export LARAVEL_URL
export REVERB_APP_KEY="${REVERB_APP_KEY:-local}"
# Reverb speaks Pusher protocol: ws://host:port/app/{key}?protocol=7&client=...&version=...
export REVERB_URL="ws://localhost:${REVERB_PORT:-6002}/app/${REVERB_APP_KEY}?protocol=7&client=python&version=1.0&flash=false"
export DB_DATABASE="postgresql://${POSTGRES_USER:-hydro}:${POSTGRES_PASSWORD:-hydro_e2e}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-hydro_e2e}"
export MQTT_HOST="localhost"
export MQTT_PORT="${MQTT_PORT:-1884}"
export LARAVEL_API_TOKEN="${LARAVEL_API_TOKEN:-dev-token-12345}"

# Проверка наличия Python зависимостей (runner)
PYTHON_BIN="python3"
if ! $PYTHON_BIN -c "import yaml, asyncio, httpx, websockets, psycopg" 2>/dev/null; then
    log_warn "Python runner dependencies missing. Creating venv and installing tests/e2e/requirements.txt..."
    VENV_DIR="$E2E_DIR/.venv"
    if [ ! -d "$VENV_DIR" ]; then
        $PYTHON_BIN -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install -r "$E2E_DIR/requirements.txt"
    PYTHON_BIN="$VENV_DIR/bin/python"
fi

# Получаем Sanctum token через /api/auth/login (нужен для /api/zones, /api/nodes, /broadcasting/auth)
log_info "Authenticating E2E user to obtain API token..."
LOGIN_JSON="$(curl -sS -X POST "$LARAVEL_URL/api/auth/login" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@example.com","password":"e2e"}')"

E2E_TOKEN="$(LOGIN_JSON="$LOGIN_JSON" $PYTHON_BIN -c 'import json,os; print((json.loads(os.environ.get("LOGIN_JSON","{}")).get("data") or {}).get("token",""))')"

if [ -z "$E2E_TOKEN" ]; then
  log_error "Failed to obtain API token from /api/auth/login. Response: $LOGIN_JSON"
  exit 1
fi

export LARAVEL_API_TOKEN="$E2E_TOKEN"
log_info "E2E API token acquired ✓"

# Запуск каждого сценария
for scenario in "${SCENARIOS[@]}"; do
    scenario_file="scenarios/${scenario}.yaml"
    
    if [ ! -f "$E2E_DIR/$scenario_file" ]; then
        log_warn "Scenario file not found: $scenario_file"
        continue
    fi
    
    log_info "Running scenario: $scenario"
    
    if (cd "$E2E_DIR" && "$PYTHON_BIN" -m runner.e2e_runner "$scenario_file"); then
        log_info "$scenario: PASSED ✓"
        PASSED=$((PASSED + 1))
    else
        log_error "$scenario: FAILED ✗"
        FAILED=$((FAILED + 1))
        FAILED_SCENARIOS+=("$scenario")
    fi
    
    # Небольшая пауза между сценариями
    sleep 2
done

# Шаг 4: Вывести отчёт
log_info "Step 4: Generating report..."

echo ""
echo "=========================================="
echo "E2E Test Summary"
echo "=========================================="
echo "Total scenarios: ${#SCENARIOS[@]}"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    log_info "All scenarios passed! ✓"
    echo ""
    echo "Reports location: $E2E_DIR/reports/"
    echo "  - junit.xml"
    echo "  - timeline.json"
    echo ""
    exit 0
else
    log_error "Some scenarios failed!"
    echo ""
    echo "Failed scenarios:"
    for scenario in "${FAILED_SCENARIOS[@]}"; do
        echo "  - $scenario"
    done
    echo ""
    echo "Reports location: $E2E_DIR/reports/"
    echo "  - junit.xml"
    echo "  - timeline.json"
    echo ""
    echo "Service logs:"
    echo "  docker-compose -f $COMPOSE_FILE logs laravel"
    echo "  docker-compose -f $COMPOSE_FILE logs history-logger"
    echo "  docker-compose -f $COMPOSE_FILE logs node-sim"
    echo ""
    exit 1
fi

