# Automation-Engine: задачи для ИИ-ассистента B (Executor Decomposition)

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** Готов к исполнению

## 1. Роль и цель

**Роль:** AI-ассистент по архитектурной декомпозиции `SchedulerTaskExecutor`.  
**Цель:** убрать god-object, разнести ответственность по модулям и оставить прозрачный coordinator.

Источник истины: `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`.

## 2. Scope ассистента

Ассистент B реализует:

- вынос логики из монолитного `scheduler_executor_impl.py` в целевые модули application/domain/infrastructure
- отказ от `exec(...)`-подгрузки и переход на явные импорты
- фиксацию публичного API `SchedulerTaskExecutor` без breaking-changes для вызывающего кода
- модульные тесты на вынесенные части + smoke-тест совместимости

## 3. Целевая декомпозиция модулей

- `application/workflow_router.py` — маршрутизация task/workflow в обработчики
- `application/workflow_validator.py` — валидация payload/контракта до исполнения
- `application/command_dispatch.py` — отправка command plans и aggregation результатов
- `application/workflow_state_sync.py` — синхронизация `workflow_phase` и persistence
- `domain/workflows/two_tank.py` — чистая доменная логика two-tank workflow
- `domain/workflows/three_tank.py` — чистая доменная логика three-tank workflow
- `domain/workflows/cycle_start.py` — cycle_start/refill flow decisions
- `scheduler_task_executor.py` — тонкий coordinator + DI + стабильный публичный интерфейс

## 4. Основные артефакты

- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/application/scheduler_executor_impl.py`
- `backend/services/automation-engine/application/*.py`
- `backend/services/automation-engine/domain/workflows/*.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/services/automation-engine/README.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` (при изменении структуры)

## 5. Обязательные правила реализации

1. Никаких поведенческих изменений в бизнес-логике без отдельного явного обоснования.  
2. Сигнатура `SchedulerTaskExecutor.execute(...)` и контракт результата остаются совместимыми.  
3. Каждый вынесенный модуль должен иметь unit-тесты на основной happy-path и fail-path.  
4. Исключить динамический `exec(...)`-лоадинг из production-кода.

## 5.1. Детальное логирование (обязательно)

При декомпозиции сохранить и стандартизировать structured-логи на границах модулей:

- `component` (`workflow_router`, `workflow_validator`, `command_dispatch`, `workflow_state_sync`)
- `zone_id`
- `task_id`
- `task_type`
- `workflow`
- `workflow_phase`
- `decision`
- `reason_code`
- `command_count`
- `duration_ms`
- `result_status` (`success`, `rejected`, `failed`)
- `correlation_id`

Обязательные точки логирования:

- вход в `execute()` и финальный результат
- выбор маршрута workflow (router)
- отклонение payload-контракта (validator)
- отправка и итог command plan (dispatch)
- синхронизация workflow_state и ошибки persistence (state_sync)

Требование к уровням:

- `INFO` для штатных переходов
- `WARNING` для деградаций/fallback
- `ERROR` для отказов исполнения/исключений

## 6. Критерии готовности (DoD)

1. `scheduler_task_executor.py` остаётся тонким coordinator-файлом (без доменной логики).  
2. Монолитный файл разбит на модули с явной ответственностью и импортами.  
3. Regression-тесты по task execution проходят на новой структуре.  
4. Документация структуры automation-engine обновлена.
5. Детальное structured-логирование присутствует на всех модульных границах и не теряет `correlation_id`.

## 7. Зависимости и handover

- Входная зависимость: ассистент A завершил и зафиксировал recovery-контракт.
- При handover финальной ветки:
 - перечислить перенесённые функции и новые модули;
 - дать mapping `old location -> new location`;
 - указать residual technical debt и следующий шаг декомпозиции.

## 8. Ограничения

- Не менять MQTT/transport контракты.
- Не внедрять изменения БД без отдельной миграции.
- Не трогать unrelated сервисы вне `automation-engine`.
