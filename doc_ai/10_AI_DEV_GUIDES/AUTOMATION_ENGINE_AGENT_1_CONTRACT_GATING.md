# Automation-Engine: задачи для ИИ-агента 1 (Contract + Gating)

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** Готов к исполнению

## 1. Роль и цель

**Роль:** AI-агент по контрактам и fail-closed политикам.  
**Цель:** закрыть входные контрактные дыры scheduler->AE и стабилизировать correction gating/sensor lifecycle.

Источник истины: `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`.

## 2. Scope агента

Агент 1 реализует:

- `P0.1` (BUG-15) — fail-closed unsupported workflow (three-tank)
- `P0.2` (BUG-17) — mandatory workflow в scheduler payload
- `P1.1` (BUG-14) — freshness correction_flags
- `P1.2` (BUG-16) — SensorModePolicy для gating-блокировок
- `P1.3` (BUG-13) — троттлинг correction-skip events

## 3. Основные артефакты

- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/config/settings.py`
- Тесты в `backend/services/automation-engine/tests/e2e/`

## 4. Критерии готовности (DoD)

1. Нет silent fallback для unknown/missing workflow (legacy default только под флагом).  
2. `stale_flags` всегда блокирует коррекции (fail-closed).  
3. Для `sensor_unstable`/`corrections_not_allowed` policy деактивации sensor mode применена.  
4. Нет event-storm по `CORRECTION_SKIPPED_MISSING_FLAGS`.  
5. E2E зелёные: `E2E-23`, `E2E-24`, `E2E-25`, `E2E-26`, `E2E-27`.

## 5. Handover следующему агенту

Передать Агенту 2:

- финальный контракт `workflow` в payload;
- список reason_code и transition policy sensor mode;
- подтверждение, что gating работает fail-closed для stale/missing flags.

## 6. Ограничения

- Не менять MQTT publishing path (только через `CommandBus`/`history-logger`).
- Не внедрять новые silent fallback.
- Не смешивать в одном PR контракты + persistence recovery + decomposition.
