# AE2_STAGE_S01_TASK.md
# Stage S1: Baseline Audit (минимальный blocking)

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** READY_FOR_EXECUTION  
**Роль:** AI-ARCH  
**Режим:** read-only audit

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Входной контекст (что прочитать)
- `AGENTS.md` (корень)
- `backend/services/AGENTS.md`
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/SYSTEM_ARCH_FULL.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/DEV_CONVENTIONS.md`

## Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_P0A_MIN_BLOCKING_AUDIT.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_SAFETY_HOTFIX_BACKLOG.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S01_TASK.md`

## Файлы, которые ЗАПРЕЩЕНО менять
- Любой production-код в `backend/services/*`
- Любые схемы БД/миграции
- MQTT контракты и namespace

## Что делать
1. Выполнить инвентаризацию command publish-path в automation-engine.
2. Зафиксировать ownership map для `executor_bound_*`, `api.py`, `scheduler/main.py`.
3. Принять и записать ownership decision по `check_phase_transitions`.
4. Сформировать минимальный safety backlog для немедленных hotfix-этапов.
5. Обновить `AE2_CURRENT_STATE.md` как межсессионный source of truth.

## Ограничения
- Не ломать pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`.
- Ноды остаются только исполнителями.
- Никаких кодовых изменений в S1 (только audit-артефакты).

## Тесты для проверки
- Проверка наличия всех S1 артефактов в `doc_ai/10_AI_DEV_GUIDES/`.
- Проверка полноты разделов: `Invariants`, `Command Flow Map`, `Ownership Map`.

## Критерий завершения
1. Все обязательные документы S1 созданы и заполнены.
2. Ownership decision по phase transitions зафиксирован как `simulation-only`.
3. `AE2_CURRENT_STATE.md` отражает закрытие S1 и готовность к mini-`S2`.
