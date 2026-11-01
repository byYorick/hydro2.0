---
name: hydro2-ae3-automation
description: Правила automation-engine / ae3lite: task_type, intents, leases, fail-closed, E-STOP/irrigation failsafe. Используй при работах в backend/services/automation-engine, scheduler-dispatch wake, zone_workflow_state, correction planner или новых AE ingress.
type: domain
lifecycle: active
---

# hydro2-ae3-automation

## Когда применять
Код/баги AE3, intents, `ae_tasks`, workflow phases, corrections, leases, operator-unblock, climate tick.

## Runtime
Канон пакета: `backend/services/automation-engine/ae3lite/`.  
Локальный SoT: `backend/services/automation-engine/AGENT.md` (имя **AGENT.md**).  
Спека: `doc_ai/04_BACKEND_CORE/ae3lite.md`.

## Ingress (не расширять без запроса)
`start-cycle`, `start-irrigation`, `start-lighting-tick`, `start-solution-topup`, `start-solution-change`, `start-climate-tick` (+ internal task status, operator-unblock).  
**Новые `task_type` запрещены без явного запроса пользователя** (hard rules).

## Инварианты (сводка AGENT.md / hard rules)
1. Нет прямого MQTT из AE или Laravel — только HL `POST /commands`.
2. Одна active execution task на зону (partial unique + `ae_zone_leases`); greenhouse climate — `greenhouse_automation_leases`.
3. Mutating success terminal = `DONE`; иначе fail.
4. Схема БД — только Laravel-миграции.
5. Нет hardcoded pH/EC targets → `PlannerConfigurationError`.
6. Integration-тесты AE — `make test-ae` / `hydro_test`, не `hydro_dev` как test DB для AE integration.

## Hard rules (defer)
`.grok/rules/hydro-hard-rules.md`, `backend/services/AGENTS.md`.

## Override внешних skills
- `laravel-11-12-app-guidelines` — полезен для Laravel стороны intents, но MQTT/AE границы задаёт Hydro.
- `docker-local-dev` — AE в core `make up`; не тащить emulator без запроса.
- `run-smoke-tests` — не заменяет `make test-ae`.

## Источники
- `doc_ai/04_BACKEND_CORE/{ae3lite,AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT,LARAVEL_AE3_READ_MODEL_CONTRACT,AE3_RUNTIME_EVENT_CONTRACT,ERROR_CODE_CATALOG,HISTORY_LOGGER_API}.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/{CORRECTION_CYCLE_SPEC,EFFECTIVE_TARGETS_SPEC,SCHEDULER_ENGINE,SCHEDULER_AE3_NON_IRRIGATION_DISPATCH}.md`
- `backend/services/automation-engine/AGENT.md`, `ae3lite/`
- `backend/services/AGENTS.md`
