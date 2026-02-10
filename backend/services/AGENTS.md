# AGENTS.md
# Правила для ИИ-агентов (backend/services)

**Дата обновления:** 2026-02-10
**Область:** `backend/services/*`

## 1) Общие правила

- Следовать корневому `AGENTS.md` и документам `doc_ai/*`.
- Разработка/тесты выполнять в Docker-контейнерах сервисов.
- Не делать ручной DDL в БД; изменения схемы только через Laravel миграции.
- Не ломать pipeline: `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.

## 2) Границы ответственности сервисов

- `scheduler`:
  - только формирует расписания;
  - отправляет абстрактные задачи в `automation-engine`;
  - отслеживает статусы задач `accepted/running/completed/failed`.
- `automation-engine`:
  - принимает scheduler tasks;
  - выполняет автоматизацию, safety-проверки, коррекции;
  - отправляет device-level команды через `history-logger/CommandBus`.
- `history-logger`:
  - ingestion телеметрии/статусов/командного потока и запись в БД.

## 3) Контракты и совместимость

- Источник целей: `/api/internal/effective-targets/batch` (Laravel).
- Для scheduler-task использовать `targets.*.execution` контракт из:
  - `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
  - `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- Любые изменения контрактов отражать в документации до/вместе с кодом.

## 4) Правила изменения кода

- Не добавлять прямые SQL-запросы к legacy recipe-таблицам, если есть Laravel API контракт.
- Предпочитать явные схемы payload и fail-closed валидацию.
- Ошибки и деградации сопровождать сервисными логами и infra-alert кодами.
- Для новых API endpoint-ов добавлять тесты и негативные сценарии.

## 5) Тестирование

- Минимум: unit/feature тесты затронутого сервиса.
- Перед сдачей прогонять:
  - `scheduler`: `pytest -q test_main.py`
  - `automation-engine`: профильные `pytest` по изменённым модулям
  - `laravel`: feature тесты для новых API endpoint-ов

## 6) Что запрещено

- Переносить device-level контроль обратно в `scheduler`.
- Обходить `history-logger` при отправке команд на узлы.
- Изменять роли/авторизацию без явной причины и тестов.
