# hydro2.0

Монорепозиторий системы управления гидропонной теплицей: прошивки ESP32, backend,
мобильное приложение, инфраструктура и полная документация.

## Быстрые ссылки

- `doc_ai/INDEX.md` — главный индекс документации
- `QUICK_START.md` — быстрый старт для разработчиков
- `doc_ai/DEV_CONVENTIONS.md` — конвенции разработки
- `backend/README.md` — backend сервисы
- `firmware/README.md` — прошивки ESP32
- `mobile/README.md` — мобильное приложение
- `infra/README.md` — инфраструктура и деплой

## Документация

- `doc_ai/` — единственный source of truth, все правки только здесь
- `doc_ai/INDEX.md` — главный навигатор по разделам

## Структура репозитория

- `backend/` — Laravel API Gateway + Python-сервисы (MQTT, автоматизация, история)
- `firmware/` — ESP-IDF прошивки нод
- `mobile/` — Android приложение
- `infra/` — docker/k8s/terraform/ansible
- `tools/` — утилиты и скрипты (в т.ч. smoke-тесты)
- `tests/` — e2e сценарии и node-sim
- `configs/` — общие конфиги проекта

Подробности структуры: `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`.

## Быстрый старт (backend dev)

```bash
make up                # поднять dev-стек
make migrate           # применить миграции
make seed              # заполнить тестовыми данными (опционально)
make logs-core         # хвост логов laravel + AE + HL + mqtt-bridge
```

Основные сервисы:
- Laravel API: http://localhost:8080
- mqtt-bridge: http://localhost:9000
- history-logger REST: http://localhost:9300
- history-logger metrics: http://localhost:9301/metrics
- automation-engine REST: http://localhost:9405
- automation-engine metrics: http://localhost:9401/metrics
- Laravel scheduler-dispatch metrics (Prometheus text): http://localhost:8080/api/system/scheduler/metrics

Поток команд к узлам (инвариант): `Laravel scheduler-dispatch → automation-engine → history-logger → MQTT → ESP32`. Подробнее: `QUICK_START.md`, `backend/README.md`, `doc_ai/ARCHITECTURE_FLOWS.md`.

## WebSocket (realtime)

- Архитектура: `backend/laravel/docs/WEBSOCKET_ARCHITECTURE.md`
- Smoke test: `tools/ws-smoke-test.sh`
- Переменные окружения:
  - Dev через nginx (рекомендуется, `backend/docker-compose.dev.yml`):
    - Frontend: только `VITE_REVERB_APP_KEY`
    - Не задаём `VITE_REVERB_HOST`/`VITE_REVERB_PORT`, клиент берёт `window.location`
  - Прямое подключение (без nginx прокси):
    - Frontend: `VITE_REVERB_APP_KEY`, `VITE_REVERB_HOST`, `VITE_REVERB_PORT`
    - Убедитесь, что CORS/origins настроены для этого режима
  - Backend: `REVERB_APP_ID`, `REVERB_APP_KEY`, `REVERB_APP_SECRET`, `REVERB_PORT`
- Запуск:
  - В dev-стеке Reverb стартует автоматически (REVERB_AUTO_START=true)
  - Вручную запускать `php artisan reverb:start` нужно только вне docker-compose

## Тестирование

- Контрактные проверки протокола: `make protocol-check`
- Laravel тесты: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test`
- Python тесты: `docker compose -f backend/docker-compose.dev.yml exec mqtt-bridge pytest`
- E2E сценарии: `tests/e2e/README.md` (детали в `doc_ai/13_TESTING/`)
- Node simulator: `tests/node_sim/README.md` (документация: `doc_ai/13_TESTING/NODE_SIM.md`)
