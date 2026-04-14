# CONTROL_MODES_SPEC.md
# Спецификация режимов управления зоной (auto / semi / manual)

**Дата создания:** 2026-04-14
**Статус:** Активный контракт

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Определить детерминированное поведение системы в трёх режимах управления
зоной: `auto`, `semi`, `manual`. Зафиксировать обязанности AE3 runtime,
Laravel scheduler, UI и rolевую модель для каждого режима.

Каноничный источник `control_mode` — `zones.control_mode` (PostgreSQL),
per-task snapshot — `ae_tasks.control_mode_snapshot`.

---

## 2. Семантика режимов

### 2.1. `auto` — полная автоматика

Hands-off. Система сама запускает циклы выращивания, переключает фазы по
истечении duration, выполняет полив по расписанию, корректирует pH/EC,
управляет fail-safe guards.

### 2.2. `semi` — полуавтомат

Recurring-операции (полив, коррекция, заполнение баков) идут автоматически.
**Все stateful решения уровня цикла** (advance phase, manual override
stages) требуют действия агронома через UI. Auto-advance фаз НЕ
выполняется — UI показывает notification "Фаза готова к переходу".

### 2.3. `manual` — ручное управление

Все этапы workflow (clean fill, solution fill, irrigation, recovery)
запускаются **только** по нажатию кнопки агронома. Auto-старт цикла из
Laravel scheduler — запрещён. AE3 runtime остаётся **полностью задействован**:
- читает probe, пишет zone events, выполняет коррекцию pH/EC,
- следит за fail-safe (level_max → auto-stop, E-Stop → fail-closed),
- ждёт `pending_manual_step` для transitions между stages.

`manual` ≠ "AE3 выключен". `manual` = "автоматика без auto-перехода между
этапами workflow и без auto-старта циклов".

---

## 3. Матрица поведения

| Действие | auto | semi | manual |
|----------|------|------|--------|
| Auto-start grow cycle (Laravel scheduler intent) | ✓ | ✓ | ✗ |
| Auto-start irrigation (cron schedule) | ✓ | ✓ | ✗ |
| Старт stage clean_fill_check | ✓ | ✓ | по кнопке `start_clean_fill` |
| Auto-progress между stages workflow | ✓ | ✓ | ✓ (level_max → ready, ждём след. кнопку) |
| Коррекция pH/EC в активном stage | ✓ | ✓ | ✓ |
| Probes / safety guards / E-Stop reconcile | ✓ | ✓ | ✓ |
| Auto-stop при `level_max` triggered | ✓ | ✓ | ✓ |
| Auto-stop при `solution_min` low | ✓ | ✓ | ✓ |
| **Auto-advance recipe phase** | ✓ (cron) | ✗ (notification) | ✗ (notification) |
| Cycle start ручной (HTTP `POST /start-cycle`) | ✓ | ✓ | ✓ |
| Manual-step `start_*` / `stop_*` | ✗ (игнор) | ✗ (игнор) | ✓ |

---

## 4. Auto-advance recipe phase

### 4.1. Триггер

Cron `phases:auto-advance` (каждые 5 минут):
1. SELECT grow_cycles WHERE
   - `zones.control_mode = 'auto'`
   - `grow_cycles.status = 'RUNNING'`
   - `current_phase.phase_started_at + duration < NOW()`
2. Для каждого подходящего цикла — guard'ы (см. §4.3), затем `advancePhase()`.

### 4.2. Стратегия определения "фаза готова"

Pluggable interface `PhaseAdvanceStrategy`:
- **`time`** (default v1): по `duration_hours + duration_days * 24` от `phase_started_at`
- **`gdd`** (заглушка v1, реализация v2): по накопленным GDD (sum(temperature - base_temp_c) от phase_started_at)
- **`dli`** (заглушка v1): по накопленному DLI (sum(light) >= dli_target)
- **`ai`** (заглушка v1): запрос к ИИ-агенту с снимком telemetry/событий/визуальных данных

Стратегия выбирается per-phase через `grow_cycle_phases.phase_advance_strategy`
(копируется из `recipe_revision_phases.phase_advance_strategy` при snapshot).

### 4.3. Guards перед auto-advance

Auto-advance **блокируется**, если:
- В зоне есть active `ae_tasks` (status IN `pending,claimed,running,waiting_command`)
- В зоне есть ACTIVE alerts с `severity IN ('error','critical')`

Если guard сработал — advance переносится на следующий tick'ation cron'а.
Не алертим по этому поводу (нормальная задержка).

### 4.4. Последняя фаза рецепта

Если `next_phase` не существует:
- Цикл **НЕ закрывается** автоматически
- Эмитится biz-alert `biz_recipe_completed_review_required` (severity `warning`,
  category `agronomy`), dedupe по `cycle_id`
- Зона продолжает работать в текущей (последней) фазе по её targets
- Дальнейшее решение (закрыть цикл / продлить / переключить рецепт) — за агрономом

### 4.5. Semi-режим: notification агроному

В `semi` cron auto-advance **не запускается**. Frontend сам показывает badge
"Фаза готова к переходу" если `phase_started_at + duration < now()`.
Кнопка `Advance phase` в UI всегда доступна агроному.

### 4.6. Semi: HTTP `POST /grow-cycles/{id}/advance-phase` guards

В semi запрос блокируется (HTTP 409) если:
- Предыдущая фаза не достигла `duration` (если стратегия `time`) — UI должен предупредить агронома, но позволить через `force=true`
- Есть active task — wait until completion (или `force=true`)

В auto/manual эндпоинт работает как сейчас (для emergency overrides).

---

## 5. Manual режим

### 5.1. Доступные `pending_manual_step` (allowed_manual_steps)

Полный набор для manual зоны:

**Старт этапов:**
- `start_clean_fill` — запустить заполнение бака чистой водой
- `start_solution_fill` — запустить заполнение раствором
- `start_prepare_recirculation` — запустить рециркуляцию для подготовки
- `start_irrigation` — запустить разовый цикл полива

**Стопы (в любой момент):**
- `stop_clean_fill`, `stop_solution_fill`, `stop_prepare_recirculation`, `stop_irrigation`, `stop_irrigation_recovery`

### 5.2. Поведение AE3 в manual

- Handlers `clean_fill / solution_fill / prepare_recirc / irrigation_check / irrigation_recovery` проверяют `control_mode == 'manual'` в начале tick и:
  - Если есть `pending_manual_step == 'stop_*'` для текущего stage → graceful stop
  - Если нет manual-step → возвращают `poll` (ждут команды)
  - Probe и коррекция продолжают работать
- При `level_max` triggered (clean tank или solution tank полон) → AE3 авто-stop текущего stage и переход в `ready`/`idle`. Следующий stage НЕ запускается без manual button.
- Коррекция pH/EC во время активного stage идёт автоматически — recipe phase targets применяются как обычно.
- Полив (`start_irrigation`) — **разовый** цикл с recipe `irrigation_duration_sec`. По завершении → `complete_ready`. Continuous-полив только при повторном `start_irrigation`.

### 5.3. Что manual НЕ делает

- НЕ переключает recipe фазу (даже если duration истёк) — agronomist сам через "Advance phase"
- НЕ принимает Laravel scheduler intents (`IRRIGATE_ONCE`, `LIGHTING_TICK` для зоны игнорируются)
- НЕ запускает cycle_start от scheduler (только HTTP от UI)

---

## 6. Переключение режимов on-the-fly

### 6.1. `auto → semi`

- Audit: `CONTROL_MODE_CHANGED` event в zone_events
- Активные tasks **продолжают выполняться** до завершения
- Cron auto-advance перестаёт обрабатывать эту зону начиная со следующего tick
- UI начинает показывать notification про phase ready

### 6.2. `auto → manual` или `semi → manual`

- Audit: `CONTROL_MODE_CHANGED` event
- Активные tasks **немедленно cancel'яются** через `CancelTaskOnControlModeChangeUseCase`:
  - AE3 эмитит graceful stop-команды (set_relay false для всех valves/pump в snapshot)
  - Task переходит в `failed` с `error_code=control_mode_switched_to_manual`
- Future scheduler intents для зоны игнорируются (Laravel side-check на `control_mode`)

### 6.3. `manual → auto` или `manual → semi`

- Audit: `CONTROL_MODE_CHANGED` event + флаг `manual_to_auto_reconcile_pending=true`
  в `zones.settings` (timestamp записан в `manual_to_auto_reconcile_requested_at`)
- **v1 reconcile (упрощённый)**: специального `manual_to_auto_cleanup` stage НЕТ.
  Вместо этого:
  1. Первая task после switch (от scheduler intent или HTTP) запускается с обычного
     `startup` stage
  2. Startup handler вызывает `_probe_irr_state` — читает фактическое hardware состояние
  3. Если что-то в нерелевантном состоянии → `irr_state_mismatch` → fail-closed
     (см. `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` §7a) → оператор получает alert
     `biz_ae3_task_failed` и разбирается руками перед следующей попыткой
  4. Если hardware чистое → обычный workflow
- Флаг `manual_to_auto_reconcile_pending` очищается при первом successful startup
  (см. §9, инвариант 7)
- **v2 (отложено)**: явный `manual_to_auto_cleanup` stage с set_relay=false
  для всех valves/pump перед `startup` — будет добавлено когда появится
  автоматический discovery node_channels для зоны

### 6.4. `semi → auto`

- Audit
- Cron auto-advance включается со следующего tick
- Активные tasks продолжают работу

---

## 7. Audit и observability

### 7.1. Zone event `CONTROL_MODE_CHANGED`

Эмитится при любом изменении `zones.control_mode`. Payload:
```json
{
  "from": "auto",
  "to": "manual",
  "user_id": 42,
  "user_role": "agronomist",
  "reason": "Emergency stop required",
  "active_task_id": 105,
  "active_task_action": "cancelled",
  "source": "ui|api|emergency"
}
```

### 7.2. Zone event `RECIPE_PHASE_ADVANCED`

Эмитится при advance phase (cron auto, ручной semi/manual, force). Payload:
```json
{
  "from_phase_index": 0,
  "to_phase_index": 1,
  "from_phase_id": 1,
  "to_phase_id": 2,
  "trigger": "auto_cron|manual_user|force",
  "user_id": null,
  "strategy": "time",
  "phase_started_at": "...",
  "phase_finished_at": "...",
  "duration_actual_sec": 3600
}
```

### 7.3. Prometheus метрики

- `ae3_phase_auto_advance_total{strategy, outcome}` — outcome: `advanced`, `blocked_active_task`, `blocked_critical_alert`, `blocked_no_next_phase`, `error`
- `ae3_control_mode_change_total{from, to, source}` — все переключения режима
- `ae3_task_cancelled_on_mode_change_total{stage}` — сколько task'ов отменилось при switch

### 7.4. Алерты

- `biz_recipe_completed_review_required` (warning, agronomy) — последняя фаза истекла, нужно решение
- `biz_phase_advance_blocked_chronic` (warning, ops) — auto-advance блокируется >24 часов подряд (что-то не так)

---

## 8. Роли и права

### 8.1. Переключение `control_mode`

| Роль | auto↔semi | →manual | manual→ |
|------|-----------|---------|---------|
| Agronomist | ✓ | ✓ | ✓ |
| Operator | ✗ | ✓ (emergency) | ✗ |
| Engineer | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ |
| Viewer | ✗ | ✗ | ✗ |

Operator может только **аварийно перевести в manual** для остановки. Возврат
в auto/semi — только через Agronomist (или выше). При operator switch в
manual — обязательное поле `reason` (хранится в audit event).

### 8.2. Advance phase

| Роль | auto | semi | manual |
|------|------|------|--------|
| Agronomist | ✓ (force) | ✓ | ✓ |
| Operator | ✗ | ✗ | ✗ |
| Engineer | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ |
| Viewer | ✗ | ✗ | ✗ |

### 8.3. Manual steps (start/stop)

| Роль | в manual | в auto/semi |
|------|----------|-------------|
| Agronomist | ✓ | ✗ |
| Operator | ✗ | ✗ |
| Engineer | ✓ | ✓ (debug) |
| Admin | ✓ | ✓ |

---

## 9. Инварианты и fail-closed

1. `zones.control_mode` — единственный source of truth. Snapshot `ae_tasks.control_mode_snapshot` имеет приоритет на уровне task (чтобы switch in-flight не сломал task в полёте).
2. AE3 НЕ имеет права самостоятельно менять `control_mode` зоны. Только Laravel ↔ UI ↔ explicit API.
3. Auto-advance phase в `semi`/`manual` запрещён даже если `force=true` от cron. Только HTTP от агронома.
4. При `auto → manual` cancel активного task обязателен — нельзя оставить runtime в "наполовину auto" состоянии.
5. Manual step `start_*` создаёт AE3 task через стандартный pipeline (`POST /zones/{id}/start-cycle` или `POST /zones/{id}/start-irrigation`), не bypass.
6. Stop-кнопки в любом режиме приоритетнее всего — это safety, не feature.
7. Флаг `zones.settings.manual_to_auto_reconcile_pending` очищается в startup
   handler после первого successful probe — именно он подтверждает hardware
   consistency. До очистки флаг виден в UI как warning indicator.

---

## 10. Что НЕ входит в v1

- AI / GDD / DLI стратегии phase advance (только `time`, остальные заложены как pluggable interface)
- Per-stage permissions гранулярнее ролей
- Multi-step undo (откат фазы назад)
- Manual coordinated batch (агроном выбирает несколько зон → одно действие на все)

Эти возможности сохраняем как future work, не блокируем ими v1.

---

## Где смотреть в коде

| Тема | Файл |
|------|------|
| `zones.control_mode` enum | `backend/laravel/database/migrations/*_zones_control_mode.php` |
| HTTP API смены режима | `app/Http/Controllers/ZoneAutomationControlModeController.php` |
| Phase model | `app/Models/GrowCycle.php`, `app/Models/GrowCyclePhase.php` |
| Manual phase advance | `app/Services/GrowCycleService.php::advancePhase()` |
| AE3 manual handler branch | `backend/services/automation-engine/ae3lite/application/handlers/*.py` (`if control_mode == 'manual'`) |
| AE3 control_mode use case | `backend/services/automation-engine/ae3lite/application/use_cases/set_control_mode.py` |
| Cron auto-advance (NEW) | `app/Console/Commands/AutoAdvancePhases.php` |
| Cancel-on-switch use case (NEW) | `backend/services/automation-engine/ae3lite/application/use_cases/cancel_task_on_mode_change.py` |
