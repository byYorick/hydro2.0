# AGENTS.md
# Правила для ИИ-агентов (backend/services)

**Дата обновления:** 2026-03-30
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
  - будит `automation-engine` только через `POST /zones/{id}/start-cycle`;
  - отслеживает lifecycle intents (`pending/claimed/running/completed/failed/cancelled`).
- `automation-engine`:
  - подхватывает intents из БД и исполняет workflow зоны;
  - выполняет автоматизацию, safety-проверки, коррекции;
  - отправляет device-level команды через `history-logger/CommandBus`.
- `history-logger`:
  - ingestion телеметрии/статусов/командного потока и запись в БД.

## 3) Контракты и совместимость

- Runtime-контракт запуска цикла: только `POST /zones/{id}/start-cycle`.
- Runtime источник данных AE3: direct SQL read-model (PostgreSQL), без runtime-зависимости от Laravel effective-targets API.
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
  - `automation-engine`: профильные `pytest` по изменённым модулям
  - `laravel`: feature тесты для новых API endpoint-ов
  - `tests/e2e`: smoke в Docker для сценария `start-cycle -> workflow`.

## 6) Что запрещено

- Вводить отдельный процесс/контейнер планировщика вне Laravel для production dispatch.
- Обходить `history-logger` при отправке команд на узлы.
- Использовать удалённые endpoint'ы `POST /scheduler/task` и `GET /scheduler/task/{task_id}` в новом runtime.
- Изменять роли/авторизацию без явной причины и тестов.
