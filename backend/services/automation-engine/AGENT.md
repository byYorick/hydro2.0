# AGENT.md (automation-engine / AE2-Lite)

Краткие инструкции для ИИ-ассистента `gpt5.3-codex` при работе в `backend/services/automation-engine`.
Обновлено: 2026-02-23
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Главная цель

Построить и поддерживать **чистый AE2-Lite** без legacy-зависимостей.

## 2. Жесткие ограничения

1. Никакого прямого MQTT из AE или Laravel.
2. Все команды к нодам идут только через `history-logger` (`POST /commands`).
3. Архитектура: один event loop, один долгоживущий runner на зону.
4. Последовательное исполнение: `send -> await terminal -> next` (успешный путь = `DONE`).
5. Поддерживаются только режимы: `auto`, `semi`, `manual`.
6. Каждый новый/изменяемый файл AE2-Lite должен быть < 400 строк.
7. Изменения схемы БД только через Laravel миграции.
8. Единственный внешний endpoint запуска цикла: `POST /zones/{id}/start-cycle`.
9. Runtime источник данных AE2-Lite: direct SQL read-model (PostgreSQL).
10. Переход к следующему шагу workflow разрешён только при статусе команды `DONE`.
11. Для топологии `two_tank_drip_substrate_trays` workflow `cycle_start` считается алиасом `startup`.
12. Legacy runtime endpoints запрещены: `POST /scheduler/task`, `GET /scheduler/task/{task_id}`.

## 3. Telemetry и feedback

1. Использовать PostgreSQL `LISTEN/NOTIFY` как основной механизм.
2. Всегда держать fallback polling для устойчивости.
3. Freshness проверять централизованно (fail-closed для critical checks).
4. `send_and_wait` завершать только по terminal statuses:
   `DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`.
5. `QUEUED|SENT|ACK` являются non-terminal и не завершают ожидание.

## 4. Политика legacy cleanup

1. Если новая реализация готова, соответствующий legacy-код удаляется в той же итерации.
2. Нельзя оставлять “временно отключенный” legacy.
3. Любой неиспользуемый код, endpoint, флаг или тест должен быть удален.
4. После крупного этапа обязателен cleanup-аудит:
   - что удалено;
   - что осталось и почему.

## 5. Приоритеты реализации

1. P0: core runtime AE2-Lite + two-tank + command gateway + notify/polling.
2. P1: correction controllers + rich zone state API.
3. P2: оптимизации и расширенная observability.

## 6. Минимальный Definition of Done (для каждой задачи)

1. Код реализован в новом AE2-Lite модуле, без новых legacy зависимостей.
2. Ненужный старый код удален.
3. Обновлены тесты (unit/integration), при необходимости e2e smoke.
4. Обновлена документация `doc_ai` при изменении контракта/схемы/поведения.
5. Изменения воспроизводимы в Docker.
6. Security-поведение не ослаблено: auth/roles/idempotency проверки сохранены тестами.

## 7. Live-smoke checklist (Scheduler -> AE)

Минимум для проверки цепочки `laravel scheduler -> /zones/{id}/start-cycle -> intent -> executor`:

1. В БД есть `zone` со статусом `online|warning`.
2. Для зоны есть активный `grow_cycle` (`PLANNED|RUNNING|PAUSED`) и `current_phase_id`.
3. Есть online-ноды требуемых типов для startup (по умолчанию минимум `irrig`).
4. Для two-tank есть `WATER_LEVEL` сенсоры clean-бака (`level_clean_max`, `level_clean_min`) и свежие значения в `telemetry_last`.
5. Доступен источник `irr_state` (иначе startup завершится `irr_state_unavailable`).
6. Проверка результата должна включать:
   - `zone_automation_intents` (status lifecycle),
   - `laravel_scheduler_active_tasks` (accepted/terminal + terminal_source),
   - `scheduler_logs` и `ae_scheduler_task_*` логи.

## 8. Типовые reason_code при fail-closed

1. `cycle_start_blocked_nodes_unavailable` — отсутствуют online-ноды обязательных типов.
2. `irr_state_unavailable` — недоступен снимок/подтверждение состояния ирригационного контура.
3. `sensor_level_unavailable|sensor_stale_detected` — нет данных уровней или телеметрия устарела.

## 9. Обязательные проверки перед merge

1. Все тесты запускать в Docker-контейнерах проекта.
2. Минимальный набор для AE2-Lite:
   - `pytest` по измененным unit/integration тестам;
   - smoke сценарий `start-cycle -> workflow terminal`.
3. Если затронуты миграции Laravel:
   - проверить `php artisan migrate` и откат `php artisan migrate:rollback`.
4. Если затронуты contracts/API:
   - прогнать тесты auth/roles/idempotency/rate-limit для затронутых endpoints.

## 10. Обновление документации при изменениях

1. Изменения БД отражать в `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
2. Изменения API/контрактов отражать в:
   - `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`;
   - `doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md` (если меняется план/статус).
3. Изменения runtime-потоков отражать в `doc_ai/ARCHITECTURE_FLOWS.md`.
4. `doc_ai/` является source of truth; `docs/` вручную не редактируется.
