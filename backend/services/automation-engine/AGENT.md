# AGENT.md (automation-engine / AE2-Lite)

Краткие инструкции для ИИ-ассистента `gpt5.3-codex` при работе в `backend/services/automation-engine`.

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
