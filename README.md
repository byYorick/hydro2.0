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

- `doc_ai/` — эталонная документация (source of truth)
- `docs/` — mirror структуры `doc_ai/` для совместимости
- Все изменения в документации вносятся только в `doc_ai/`

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
cd backend
docker compose -f docker-compose.dev.yml up -d --build
```

Основные сервисы:
- Laravel API: http://localhost:8080
- mqtt-bridge: http://localhost:9000
- history-logger metrics: http://localhost:9301/metrics
- automation-engine metrics: http://localhost:9401/metrics
- scheduler metrics: http://localhost:9402/metrics

Больше деталей: `backend/README.md` и `backend/services/README.md`.

## WebSocket (realtime)

- Архитектура: `backend/laravel/docs/WEBSOCKET_ARCHITECTURE.md`
- Smoke test: `tools/ws-smoke-test.sh`
- Переменные окружения:
  - Frontend: `VITE_REVERB_APP_KEY`, `VITE_REVERB_HOST`, `VITE_REVERB_PORT`
  - Backend: `REVERB_APP_ID`, `REVERB_APP_KEY`, `REVERB_APP_SECRET`, `REVERB_PORT`
- Запуск: `php artisan reverb:start`

## Тестирование

- Контрактные проверки протокола: `make protocol-check`
- Laravel тесты: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test`
- Python тесты: `docker compose -f backend/docker-compose.dev.yml exec mqtt-bridge pytest`
- E2E сценарии: `tests/e2e/README.md`
- Node simulator: `tests/node_sim/README.md`
