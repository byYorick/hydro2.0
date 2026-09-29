# AGENTS.md
# Правила для ИИ-агентов (backend/services)

**Дата обновления:** 2026-09-24
**Область:** `backend/services/*`

## 1) Общие правила

- Следовать корневому `AGENTS.md` и документам `doc_ai/*`.
- Разработка/тесты выполнять в Docker-контейнерах сервисов.
- Не делать ручной DDL в БД; изменения схемы только через Laravel миграции.
- Не ломать pipeline: `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.

## 2) Границы ответственности сервисов

- `laravel`:
  - владеет схемой БД, API, UI;
  - диспетчера `automation:dispatch-schedules` нет (волна 10);
  - не публикует команды в MQTT напрямую.
- `automation-engine`:
  - канонический runtime — `ae4/` (AE 1.0.0);
  - **локальный SoT-контракт сервиса:** `backend/services/automation-engine/AGENT.md`;
  - полный канон поведения — `doc_ai/04_BACKEND_CORE/ae4.md`;
  - тик сам назначает полив/химию/свет и один climate-tick на теплицу;
  - отправляет device-level команды через `history-logger` (`POST /commands`).
- `history-logger`:
  - ingestion телеметрии/статусов/командного потока и запись в БД;
  - единственная точка публикации команд в MQTT.

## 3) Контракты и совместимость

- HTTP automation-engine: `/health`, `/metrics`, `/zones/{id}/state`, control-mode,
  operator-unblock, `POST /greenhouses/{id}/start-climate-tick`.
- Маршрутов `start-irrigation`, `start-lighting-tick`, `start-solution-topup`,
  `start-cycle`, `start-solution-change` нет.
- Runtime читает zone state из PostgreSQL SQL read-model, без runtime HTTP к Laravel.
- Любые изменения контрактов отражать в документации до/вместе с кодом.

## 4) Правила изменения кода

- Не использовать runtime HTTP-запросы в Laravel для read-model автоматики.
- Прямой SQL read-model в AE разрешён и обязателен для runtime path.
- Предпочитать явные схемы payload и fail-closed валидацию.
- Ошибки и деградации сопровождать сервисными логами и infra-alert кодами.
- Для новых API endpoint-ов добавлять тесты и негативные сценарии.

## 5) Тестирование

- Минимум: unit/feature тесты затронутого сервиса.
- Перед сдачей прогонять:
  - `automation-engine`: `make test-ae` / `pytest` по `tests/unit/ae4`
  - `laravel`: feature тесты для новых API endpoint-ов
  - `tests/e2e`: smoke в Docker для релевантного пути.

## 6) Что запрещено

- Вводить отдельный процесс/контейнер планировщика вне Laravel для production wake-up зон
  (тик AE сам будит зоны).
- Обходить `history-logger` при отправке команд на узлы.
- Прямой MQTT из automation-engine.
- Изменять роли/авторизацию без явной причины и тестов.
- Называть `ae3lite` текущим runtime.
