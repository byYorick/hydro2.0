hydro2.0 Monorepo (skeleton)

Скелет проекта, созданный по спецификации `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`.

Структура верхнего уровня:
- `doc_ai/` — **основная документация** (эталон, не изменяется)
- `docs/` — mirror структуры из `doc_ai/` (для совместимости)
- `firmware/` — прошивки для ESP32 (ESP-IDF)
- `backend/` — серверные сервисы (API, MQTT-мост, автоматизация, история)
- `mobile/` — мобильное приложение
- `infra/` — инфраструктура и деплой
- `tools/` — утилиты и генераторы
- `configs/` — общие конфиги системы

**Документация:**
- Основная документация: `doc_ai/` — эталонная документация проекта
- Папка `docs/` является mirror структуры из `doc_ai/` для совместимости
- Все изменения в документации вносятся только в `doc_ai/`
- **Начните с:** `doc_ai/INDEX.md` — главный индекс документации
- Статус реализации: `doc_ai/IMPLEMENTATION_STATUS.md`
- Roadmap: `doc_ai/ROADMAP_2.0.md`

**Приоритеты разработки:**
- См. приоритеты: `doc_ai/DEVELOPMENT_PRIORITIES.md`

**WebSocket (Real-time обновления):**
- Архитектура: `backend/laravel/docs/WEBSOCKET_ARCHITECTURE.md`
- Smoke test: `tools/ws-smoke-test.sh`

**Конфигурация WebSocket:**
- Frontend переменные: `VITE_REVERB_APP_KEY`, `VITE_REVERB_HOST`, `VITE_REVERB_PORT`
- Backend переменные: `REVERB_APP_ID`, `REVERB_APP_KEY`, `REVERB_APP_SECRET`, `REVERB_PORT`
- Запуск Reverb: `php artisan reverb:start`

См. подробности в `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`.


