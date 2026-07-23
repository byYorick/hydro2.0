---
name: two-tank-debug
description: Диагностика застрявшего two-tank startup workflow зоны. Используй когда зона не проходит idle/startup → tank_filling → tank_recirc → ready → irrigating → ready, зависла в промежуточной фазе, или корректировки pH/EC не запускаются.
---

# Two-Tank Startup Workflow — Диагностика

Различай два уровня состояния:

| Уровень | Где смотреть | Примеры |
|---------|--------------|---------|
| **`workflow_phase`** | `zone_workflow_state.workflow_phase` | `idle`, `tank_filling`, `tank_recirc`, `ready`, `irrigating` |
| **`stage`** | `ae_tasks.current_stage` / `payload.ae3_cycle_start_stage` | `startup`, `clean_fill_check`, `solution_fill_check`, `prepare_recirculation_check`, `complete_ready` |

Канонический happy-path stages (`cycle_start`):

```
startup (phase=idle)
  → clean_fill_* (phase=tank_filling)
  → solution_fill_* (phase=tank_filling)   # Ca-only (pump_b), без pH
  → prepare_recirculation_* (phase=tank_recirc)  # sequential pipeline + dilute
  → complete_ready (phase=ready)
```

Полив — отдельный task `irrigation_start` (только при `workflow_phase=ready`):

```
await_ready → decision_gate → irrigation_* (phase=irrigating)
  → irrigation_stop_to_ready (phase=ready)
```

Химия по фазам:
- **fill** (`solution_fill_check`) — только calcium (`pump_b`); pH на fill **не канон**
- **recirc** (`prepare_recirculation_check`) — sequential Ca→pH→… + dilute-on-overshoot
- **irrig** (`irrigation_check`) — только pH inline; без EC dose / recovery chemistry

`irrig_recirc` / `irrigation_recovery_*` / `irrigation_stop_to_recovery` — **не happy-path**
(removed from canon; legacy DB rows → migrate via `irrigation_stop_to_ready`).

Коррекции открываются **внутри check-stages** с `has_correction=True` в
[`workflow_topology.py`](backend/services/automation-engine/ae3lite/application/services/workflow_topology.py):
`solution_fill_check`, `prepare_recirculation_check`, `irrigation_check`.
Отдельного `WORKFLOW_CORRECTION_OPEN_PHASES` больше нет.

## Шаг 0 — Уточни zone_id

Спроси у пользователя `zone_id` если не указан. Все запросы ниже идут к `hydro_dev` через локальный `psql` (host=localhost:5432 user=hydro).

**Auth (обязательно):** TCP-логин требует пароль. Не вызывай голый `psql` без credentials — в non-interactive shell он зависнет на `Password for user hydro:`. Используй одно из:
- `~/.pgpass` (`localhost:5432:*:hydro:hydro`, `chmod 600`) — предпочтительно;
- `PGPASSWORD=hydro` перед командой (dev-пароль из `docker-compose.dev.yml`);
- флаг `-w` (never prompt), чтобы при отсутствии credentials сразу получить ошибку, а не hang.

Пример префикса: `PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "..."`.

## Шаг 1 — Текущая фаза workflow

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT workflow_phase, payload->>'ae3_cycle_start_stage' AS stage, updated_at FROM zone_workflow_state WHERE zone_id=<ID>"
```

Если пусто — зона не инициализирована для two-tank. Если `workflow_phase` ∈ `{idle,tank_filling,tank_recirc}` и `updated_at` старше 10 мин при active task — **вероятно stuck**.
Если видишь `irrig_recirc` — legacy row; канон после полива — `ready`.

## Шаг 2 — Последние workflow-события

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT type, payload_json->>'phase', payload_json->>'reason', created_at FROM zone_events WHERE zone_id=<ID> AND (type LIKE '%WORKFLOW%' OR type LIKE '%PHASE%' OR type LIKE '%FILL%' OR type LIKE '%RECIRC%' OR type LIKE '%CORRECTION%') ORDER BY created_at DESC LIMIT 15"
```

Ищи: `*_TIMEOUT`, `LEVEL_SWITCH_CHANGED`, `CLEAN_FILL_*`, `SOLUTION_FILL_*`, `RECIRCULATION_*`, `TWO_TANK_*`, `CORRECTION_*`, `WATER_BASELINE_*`, `PIPELINE_STEP_*`, `RECIRC_DILUTE_*`.

## Шаг 3 — Active task

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT id, task_type, status, current_stage, workflow_phase, details, updated_at FROM ae_tasks WHERE zone_id=<ID> AND status IN ('pending','claimed','running','waiting_command') ORDER BY created_at DESC"
```

Если таблица/колонки отличаются в окружении — смотри `zone_automation_tasks` / JSON `workflow`.  
Если `status='waiting_command'` и нет недавних command responses — команда потерялась. Если `status='running'` > 5 мин — probable hang.
Если `current_stage` содержит `irrigation_recovery` — не канон; ожидается `irrigation_stop_to_ready` → `ready`.

## Шаг 4 — Water level sensors

Критично для two-tank.

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT metric_type, value, ts FROM telemetry_last WHERE zone_id=<ID> AND metric_type IN ('LEVEL_CLEAN_MIN','LEVEL_CLEAN_MAX','LEVEL_SOLUTION_MIN','LEVEL_SOLUTION_MAX')"
```

Интерпретация:
- `LEVEL_CLEAN_MAX=0` на startup → ожидается `clean_fill` (клапан `valve_clean_fill` ON).
- `LEVEL_CLEAN_MAX=1` → clean_fill пропускается / завершается.
- `LEVEL_SOLUTION_MAX=1` → solution_fill complete.
- Все `0` после fill → датчики не latched / узел перезагружался / broken wire / sim latch-delay.

Production-нода **не** публикует `clean_fill_source_empty`; пустой источник clean → AE3 timeout/retry (`clean_fill_timeout_sec`, `clean_fill_retry_cycles`).

## Шаг 5 — Узлы зоны и их online-статус

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT n.uid, n.type, n.status, n.last_seen_at FROM nodes n JOIN node_zones nz ON nz.node_id=n.id WHERE nz.zone_id=<ID>"
```

Если irrig/storage узел offline — fill-команды не дойдут → зависание в `clean_fill_*` / `solution_fill_*`.

## Шаг 6 — Последние команды fill/drain

```
PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -c "SELECT cmd, status, node_uid, channel, payload, created_at FROM commands WHERE zone_id=<ID> AND created_at > now() - interval '30 minutes' ORDER BY created_at DESC LIMIT 20"
```

Флаги для отчёта:
- `status='INVALID'` → ошибка payload.
- `status='ERROR'` + `estop_active` → E-Stop удерживается (ON-команды отвергаются нодой).
- `status='ERROR'` → узел отверг (interlock, cooldown, I2C, safe-limit).
- `status='TIMEOUT'` → нет response от узла.
- `status='NO_EFFECT'` → 3 подряд для pid_type → alert + fail-closed.
- На fill ожидай dose только на `pump_b` (Ca); `pump_acid`/`pump_base` на fill — drift от канона.
- На irrig ожидай pH-only; EC dose на irrig — drift.

## Шаг 7 — Correction gate

Проверь, что active stage — один из correction-capable check-stages (см. выше).  
В `ready` без активного check-stage коррекции не идут (кроме topup/irrigation path).

```
rg -n "has_correction=True" backend/services/automation-engine/ae3lite/application/services/workflow_topology.py
```

## Шаг 8 — AE3 runtime state

```
curl -s http://localhost:9405/zones/<ID>/state | jq .
```

Сверь `workflow_phase` / stage с БД (шаг 1). Расхождение = проблема синхронизации read-model.

## Итоговый отчёт

Структурируй вывод по секциям Шагов. В **конце** — краткий вердикт:
- **Где застряла:** `workflow_phase=X`, `stage=Y`, с момента Z
- **Вероятная причина:** (A) команда не дошла / (B) level sensors / (C) task hung / (D) узел offline / (E) correction не открыт на этом stage / (F) E-Stop / (G) stage timeout / (H) chemistry drift (fill≠Ca-only или irrig≠pH-only)
- **Рекомендованное действие** (не выполняй без подтверждения пользователя):
  - Если stuck и задача hung → предложить `/fix-stuck-zone <ID>`.
  - Если levels = 0 после fill → перезапустить `POST /zones/<ID>/start-cycle`.
  - Если узел offline → проверить firmware/power.
  - Если `estop_active` → снять E-Stop и проверить restore snapshot.

**Ничего destructive не делай без явного "да" от пользователя.**
