# AGENTS.md
# Правила для ИИ-агентов (backend/services)

**Дата обновления:** 2026-08-02
**Область:** `backend/services/*`

## 1) Общие правила

- Следовать корневому `AGENTS.md` и документам `doc_ai/*`.
- Разработка/тесты выполнять в Docker-контейнерах сервисов.
- Не делать ручной DDL в БД; изменения схемы только через Laravel миграции.
- Не ломать pipeline: `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.

## 2) Границы ответственности сервисов

- `laravel` scheduler-dispatch:
  - формирует расписания;
  - пишет intent в БД (`zone_automation_intents`);
  - будит `automation-engine` по типу задачи (не всё идёт в `start-cycle`):
    - полив — `POST /zones/{id}/start-irrigation`;
    - lighting tick (AE3) — `POST /zones/{id}/start-lighting-tick`;
    - solution topup/change — `POST /zones/{id}/start-solution-topup` / `start-solution-change`;
    - greenhouse climate — `POST /greenhouses/{id}/start-climate-tick`;
    - diagnostics / cycle_start / остальные compat non-irrigation — `POST /zones/{id}/start-cycle`
      (см. `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`);
  - отслеживает lifecycle intents (`pending/claimed/running/completed/failed/cancelled`).
- `automation-engine`:
  - канонический runtime — `ae3lite/`;
  - **локальный SoT-контракт сервиса:** `backend/services/automation-engine/AGENT.md`
    (имя файла `AGENT.md`, не `AGENTS.md`); дополняет этот документ;
  - подхватывает intents / wake-up ingress и исполняет workflow зоны;
  - выполняет автоматизацию, safety-проверки, коррекции;
  - отправляет device-level команды через `history-logger` (`POST /commands`).
- `history-logger`:
  - ingestion телеметрии/статусов/командного потока и запись в БД;
  - единственная точка публикации команд в MQTT.

## 3) Контракты и совместимость

- Внешние ingress AE3: `start-cycle`, `start-irrigation`, `start-lighting-tick`,
  `start-solution-topup`, `start-solution-change`, `start-climate-tick`
  (+ internal `GET /internal/tasks/{task_id}`).
  Полный канон — `doc_ai/04_BACKEND_CORE/ae3lite.md` и `automation-engine/AGENT.md`.
- Runtime источник данных AE3: direct SQL read-model (PostgreSQL) + compiled bundles,
  без runtime-зависимости от Laravel effective-targets API.
- LISTEN/NOTIFY AE3: `scheduler_intent_terminal`, `ae_zone_event`; команды — polling
  (не `ae_command_status` / `ae_signal_update`).
- Для intent lifecycle использовать контракт из:
  - `doc_ai/04_BACKEND_CORE/ae3lite.md`
  - `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- Любые изменения контрактов отражать в документации до/вместе с кодом.

## 4) Правила изменения кода

- Не использовать runtime HTTP-запросы в Laravel для read-model автоматики.
- Прямой SQL read-model в AE3 разрешен и обязателен для runtime path.
- Предпочитать явные схемы payload и fail-closed валидацию.
- Ошибки и деградации сопровождать сервисными логами и infra-alert кодами.
- Для новых API endpoint-ов добавлять тесты и негативные сценарии.

## 5) Тестирование

- Минимум: unit/feature тесты затронутого сервиса.
- Перед сдачей прогонять:
  - `automation-engine`: `make test-ae` / профильные `pytest` по изменённым модулям
  - `laravel`: feature тесты для новых API endpoint-ов
  - `tests/e2e`: smoke в Docker для релевантного ingress → workflow.

## 6) Что запрещено

- Вводить отдельный процесс/контейнер планировщика вне Laravel для production dispatch.
- Обходить `history-logger` при отправке команд на узлы.
- Использовать удалённые endpoint'ы `POST /scheduler/task` и `GET /scheduler/task/{task_id}` в новом runtime.
- Изменять роли/авторизацию без явной причины и тестов.
