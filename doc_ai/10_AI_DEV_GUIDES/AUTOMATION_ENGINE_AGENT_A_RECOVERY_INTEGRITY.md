# Automation-Engine: задачи для ИИ-ассистента A (Recovery + Workflow Integrity)

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** Готов к исполнению

## 1. Роль и цель

**Роль:** AI-ассистент по функциональной корректности recovery и целостности workflow-контракта.  
**Цель:** обеспечить безопасное продолжение in-flight workflow после рестарта и исключить некорректный restart фаз.

Источник истины: `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`.

## 2. Scope ассистента

Ассистент A реализует:

- fix recovery выбора `workflow`/`workflow_stage` из `zone_workflow_state.payload`
- fail-safe обработку повреждённых/неполных записей `zone_workflow_state` без падения всего recovery-цикла
- унификацию контракта `workflow_stage` vs `workflow_phase` в recovery-path
- тесты на продолжение check-фаз после рестарта (без повторного запуска startup-команд)

## 3. Основные артефакты

- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/application/scheduler_executor_impl.py`
- `backend/services/automation-engine/infrastructure/workflow_state_store.py`
- `backend/services/automation-engine/test_api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` (при изменении контракта)

## 4. Обязательные правила реализации

1. Recovery должен продолжать **конкретную check-фазу** (`clean_fill_check`, `solution_fill_check`, `prepare_recirculation_check`, `irrigation_recovery_check`), если фаза известна.  
2. Любая невалидная запись одной зоны не должна останавливать recovery остальных зон.  
3. Для неизвестного/пустого workflow использовать fail-closed или явный fallback по фазе, но без silent restart `startup`.  
4. Логи/события recovery должны содержать `zone_id`, исходную фазу, выбранный workflow, причину fallback.

## 4.1. Детальное логирование (обязательно)

Для каждого обработанного `zone_workflow_state` писать structured-лог с полями:

- `component=workflow_state_recovery`
- `zone_id`
- `workflow_phase_source`
- `workflow_phase_normalized`
- `workflow_selected`
- `scheduler_task_id_previous`
- `recovery_action` (`enqueue_continuation`, `stale_stop`, `skip_invalid`, `skip_idle_ready`, `failed`)
- `reason_code`
- `state_age_sec`
- `correlation_id` (если есть)
- `enqueue_id` (если создан)

Дополнительно:

- при fallback workflow — warning-лог + zone_event с полями `fallback_from`/`fallback_to`
- при невалидной записи — warning-лог с причиной (`invalid_zone_id`, `invalid_payload`, `invalid_phase`)
- при исключении — error-лог с `error_type`, `error_message`, `trace_id`

## 5. Критерии готовности (DoD)

1. После рестарта in-flight фазы продолжаются корректно, без повторного запуска стартовых команд.  
2. Recovery устойчив к битым данным в `zone_workflow_state`.  
3. Тесты покрывают:
 - корректный resume для `tank_filling`, `tank_recirc`, `irrig_recirc`;
 - сценарий с невалидной записью в одной зоне и успешным recovery для другой;
 - отсутствие silent restart в `startup`.
4. Контракт recovery задокументирован в спецификации scheduler↔automation.
5. Детальное structured-логирование recovery включено и проверено в тестах/фикстурах по ключевым веткам.

## 6. Зависимости и handover

- Входная зависимость: базовая логика Agent 1/2 уже в ветке (контракты workflow_phase стабилизированы).
- Выходной handover ассистенту B:
 - финальный контракт полей recovery payload;
 - список точек интеграции, которые нельзя ломать при декомпозиции;
 - перечень критичных regression-тестов.

## 7. Ограничения

- Не менять путь публикации команд: только через `CommandBus`/`history-logger`.
- Не делать ручной DDL; если нужна схема — только Laravel migration.
- Не смешивать крупную архитектурную декомпозицию в PR этого ассистента.
