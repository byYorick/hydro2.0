# Automation-Engine: задачи для ИИ-агента 2 (Workflow Coordination)

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** Готов к исполнению

## 1. Роль и цель

**Роль:** AI-агент по координации workflow между SchedulerTaskExecutor и ZAS.  
**Цель:** устранить конфликт двух контуров автоматизации и синхронизировать действия по `workflow_phase`.

Источник истины: `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`.

## 2. Scope агента

Агент 2 реализует:

- `P2.1` (BUG-02, BUG-04) — per-zone `workflow_phase` и синхронизация переходов
- `P2.2` (часть BUG-02) — блокировка irrigation по `workflow_phase`
- `P2.3` (BUG-03) — фазное разделение EC-компонентов
- `P2.4` (BUG-01, BUG-06) — sensor mode activation ownership у workflow + inline-коррекция
- `P2.5` (BUG-07) — PID reset при `tank_recirc -> irrigating`

## 3. Canonical naming (обязательно)

- `workflow_stage`: `startup`, `clean_fill_check`, `solution_fill_check`, `prepare_recirculation_check`, `irrigation_recovery`, `irrigation_recovery_check`.
- `workflow_phase`: `idle`, `tank_filling`, `tank_recirc`, `ready`, `irrigating`, `irrig_recirc`.

Любой новый код/тест должен использовать именно этот нейминг.

## 4. Основные артефакты

- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/irrigation_controller.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/services/pid_state_manager.py`
- Тесты в `backend/services/automation-engine/tests/e2e/`

## 5. Критерии готовности (DoD)

1. ZAS не запускает полив, если `workflow_phase` не `ready`/`irrigating`.  
2. В `tank_filling`/`tank_recirc` дозируется только `npk`; в `irrigating`/`irrig_recirc` только `calcium/magnesium/micro`.  
3. Sensor mode активируется workflow и не активируется ZAS по `missing_flags`.  
4. PID интеграл сбрасывается на переходе `tank_recirc -> irrigating`.  
5. E2E зелёные: `E2E-01`, `E2E-09`, `E2E-10`, `E2E-11`, `E2E-12`, `E2E-13`.

## 6. Зависимости и handover

- Входная зависимость: этапы `P0` и `P1` завершены (Агент 1).
- Выходной handover Агенту 3:
  - стабильный контракт `workflow_phase`;
  - подтверждённая координация ZAS/workflow;
  - список новых/изменённых reason_code и событий.

## 7. Ограничения

- Не менять ownership: sensor mode activation только workflow.
- Не добавлять прямой publish в MQTT вне `history-logger/CommandBus`.
- Не менять persistence recovery (`P4`) в рамках этого scope.
