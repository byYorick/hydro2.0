---
name: two-tank-debug
description: Диагностика застрявшего two-tank startup workflow зоны. Используй когда зона не проходит startup → clean_fill → solution_fill → prepare_recirculation → READY → irrig_recirc, зависла в промежуточной фазе, или корректировки pH/EC не запускаются.
---

# Two-Tank Startup Workflow — Диагностика

Канонический порядок фаз: `startup → clean_fill → solution_fill → prepare_recirculation → READY → irrig_recirc`.

Корректировки pH/EC разрешены только в фазах из `WORKFLOW_CORRECTION_OPEN_PHASES` (см. [backend/services/automation-engine/services/zone_automation_constants.py](backend/services/automation-engine/services/zone_automation_constants.py)). `irrig_recirc` должен быть в списке — иначе корректировки не запустятся даже при правильной фазе.

## Шаг 0 — Уточни zone_id

Спроси у пользователя `zone_id` если не указан. Все запросы ниже идут к `hydro_dev` через локальный `psql` (host=localhost:5432 user=hydro).

## Шаг 1 — Текущая фаза workflow

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT workflow_phase, payload->>'workflow', updated_at FROM zone_workflow_state WHERE zone_id=<ID>"
```

Если пусто — зона не инициализирована для two-tank. Если фаза `startup/clean_fill/solution_fill/prepare_recirculation` и `updated_at` старше 10 мин — **вероятно stuck**.

## Шаг 2 — Последние workflow-события

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT type, payload_json->>'phase', payload_json->>'reason', created_at FROM zone_events WHERE zone_id=<ID> AND type LIKE '%WORKFLOW%' OR type LIKE '%PHASE%' ORDER BY created_at DESC LIMIT 15"
```

Ищи: `*_PHASE_TRANSITION_FAILED`, `*_TIMEOUT`, `level_switch_changed`, `TWO_TANK_*`.

## Шаг 3 — Active task

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT id, status, workflow, details FROM zone_automation_tasks WHERE zone_id=<ID> AND status IN ('pending','claimed','running','waiting_command') ORDER BY created_at DESC"
```

Если `status='waiting_command'` и нет недавних command responses — команда потерялась. Если `status='running'` > 5 мин — probable hang.

## Шаг 4 — Water level sensors

Критично для two-tank. После fill-а уровни должны быть `latched=1`.

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT metric_type, value, ts FROM telemetry_last WHERE zone_id=<ID> AND metric_type IN ('LEVEL_CLEAN_MIN','LEVEL_CLEAN_MAX','LEVEL_SOLUTION_MIN','LEVEL_SOLUTION_MAX')"
```

Если **все значения = 0** → `check_water_level()` вернёт False → корректировки заблокированы. Типовые причины:
- Узел перезагружался и сбросил latch (нужен новый fill cycle).
- Датчики не физически подключены / broken wire.
- В dev-симуляторе — не отработали latch-delay-ы (10s/30s/60s в test_node).

## Шаг 5 — Узлы зоны и их online-статус

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT n.uid, n.type, n.status, n.last_seen_at FROM nodes n JOIN node_zones nz ON nz.node_id=n.id WHERE nz.zone_id=<ID>"
```

Если насосный узел (`pump_node`) offline — fill-команды не дойдут → зависание в `clean_fill`/`solution_fill`.

## Шаг 6 — Последние команды fill/drain

```
psql -h localhost -U hydro -d hydro_dev -c "SELECT cmd, status, node_uid, channel, payload, created_at FROM commands WHERE zone_id=<ID> AND created_at > now() - interval '30 minutes' ORDER BY created_at DESC LIMIT 20"
```

Флаги для отчёта:
- `status='INVALID'` → ошибка payload, смотри reason.
- `status='ERROR'` → узел отверг (I2C fail, safe-limit, etc.).
- `status='TIMEOUT'` → нет response от узла.
- `status='NO_EFFECT'` → команда прошла но state не изменился (3 подряд для pid_type → alert + fail-closed).

## Шаг 7 — Correction gate (`irrig_recirc` разрешён?)

Grep в коде:
```
grep -n "WORKFLOW_CORRECTION_OPEN_PHASES" backend/services/automation-engine/services/zone_automation_constants.py
```

Убедись что `"irrig_recirc"` присутствует в списке. Если нет — это баг (memory хранит факт что он был добавлен в коммите, регресс = немедленный flag).

## Шаг 8 — AE3 runtime state

```
curl -s http://localhost:9405/zones/<ID>/state | jq .
```

Сверь `workflow_phase` с тем что в БД (шаг 1). Расхождение = проблема синхронизации read-model.

## Итоговый отчёт

Структурируй вывод по секциям Шагов. В **конце** — краткий вердикт:
- **Где застряла:** фаза X, с момента Y
- **Вероятная причина:** (A) команда не дошла / (B) level sensors не latched / (C) task hung / (D) узел offline / (E) gate blocks correction
- **Рекомендованное действие** (не выполняй без подтверждения пользователя):
  - Если stuck и задача hung → предложить `/fix-stuck-zone <ID>` (разблокирует DELETE zone_workflow_state).
  - Если level sensors = 0 → перезапустить fill workflow через `POST /zones/<ID>/start-cycle`.
  - Если узел offline → проверить firmware/power.

**Ничего destructive не делай без явного "да" от пользователя.**
