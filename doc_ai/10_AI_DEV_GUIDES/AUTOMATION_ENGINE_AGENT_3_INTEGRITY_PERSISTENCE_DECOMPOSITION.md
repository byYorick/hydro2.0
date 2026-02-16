# Automation-Engine: задачи для ИИ-агента 3 (Integrity + Persistence + Decomposition)

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** Готов к исполнению

## 1. Роль и цель

**Роль:** AI-агент по целостности событий, recovery и архитектурной декомпозиции.  
**Цель:** обеспечить корректную семантику событий, recovery после рестарта и вынос логики из god-object.

Источник истины: `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`.

## 2. Scope агента

Агент 3 реализует:

- `P3.1` (BUG-10) — bootstrap первого автополива
- `P3.2` (BUG-11) — события только после подтверждённого publish
- `P3.3` (BUG-08) — zone guards default ON
- `P3.4` (BUG-12) — политика компенсации partial EC batch
- `P4.1` (BUG-05) — persistence `zone_workflow_state`
- `P4.2` — startup recovery для in-flight workflows
- `P5.1` (BUG-09) — декомпозиция `scheduler_task_executor.py`

## 3. Основные артефакты

- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/irrigation_controller.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/infrastructure/command_bus.py`
- `backend/services/automation-engine/scheduler_task_executor.py`
- Новые модули по целевой структуре P5
- Миграции Laravel для `zone_workflow_state`
- Тесты в `backend/services/automation-engine/tests/e2e/`

## 4. Критерии готовности (DoD)

1. Нет фантомных событий успешного действия при publish failure.  
2. Первый автополив работает без исторического `IRRIGATION_STARTED`.  
3. Zone guards включены по умолчанию в коде и окружении разработки.  
4. Recovery после рестарта восстанавливает in-flight workflow без зависших фаз.  
5. `scheduler_task_executor.py` превращён в тонкий coordinator (<800 строк).  
6. E2E зелёные: `E2E-14..E2E-22` + полный `E2E-01..E2E-27` на завершении P5.

## 5. Зависимости и handover

- Входная зависимость: этап `P2` завершён (Агент 2), этапы `P0-P1` завершены (Агент 1).
- На P4/P5 использовать уже стабилизированный `workflow_phase` контракт.

## 6. Документация, обязательная к обновлению

- `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` (если меняется интеграция фаз)
- `backend/services/automation-engine/README.md`

## 7. Ограничения

- Все изменения БД только через Laravel migration.
- Никакой прямой MQTT publish из scheduler/automation/Laravel.
- Не объединять в один PR несвязанные подсистемы (следовать quality gates из audit plan).
