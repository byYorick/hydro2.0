# AE3 Configuration Parameter Inventory

**Версия:** 1.0 (Phase 0 discovery output)
**Дата:** 2026-04-15
**Статус:** исходник для рефакторинга, см. [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md)

Полный инвентарь параметров конфигурации automation runtime. Охватывает:
- 19 namespaces в Laravel `AutomationConfigRegistry`
- Все поля `zone.correction` (48+ параметров) с bounds/defaults
- Compile pipeline (system → zone → cycle)
- AE3 Python resolver (`two_tank_runtime_spec.py`)
- Python-side hardcoded defaults (которые нужно удалить)

---

## 1. Namespaces (AutomationConfigRegistry)

Источник: [AutomationConfigRegistry.php:11-35](backend/laravel/app/Services/AutomationConfigRegistry.php#L11-L35)

| # | Namespace | Scope | Schema v | Required | Default source |
|---|---|---|---|---|---|
| 1 | `system.runtime` | system | 1 | ✓ | `AutomationRuntimeConfigService::defaultSettingsMapStatic()` |
| 2 | `system.automation_defaults` | system | 1 | ✓ | `SystemAutomationSettingsCatalog` |
| 3 | `system.command_templates` | system | 1 | ✓ | `SystemAutomationSettingsCatalog` |
| 4 | `system.process_calibration_defaults` | system | 1 | ✓ | `SystemAutomationSettingsCatalog` |
| 5 | `system.pump_calibration_policy` | system | 1 | ✓ | `SystemAutomationSettingsCatalog` |
| 6 | `system.sensor_calibration_policy` | system | 1 | ✓ | `SystemAutomationSettingsCatalog` |
| 7 | `system.alert_policies` | system | 1 | ✓ | `{ae3_operational_resolution_mode: 'manual_ack'}` |
| 8 | `greenhouse.logic_profile` | greenhouse | 1 | — | `{active_mode: null, profiles: {}}` |
| 9 | `zone.logic_profile` | zone | 1 | ✓ | `{active_mode: null, profiles: {}}` |
| 10 | `zone.correction` | zone | 1 | ✓ | `ZoneCorrectionConfigCatalog::defaults()` |
| 11 | `zone.pid.ph` | zone | 1 | ✓ | `ZonePidDefaults::forType('ph')` |
| 12 | `zone.pid.ec` | zone | 1 | ✓ | `ZonePidDefaults::forType('ec')` |
| 13 | `zone.runtime_tuning_bundle` | zone | 1 | ✓ | preset selector + overrides |
| 14 | `zone.process_calibration.generic` | zone | 1 | ✓ | `ZoneProcessCalibrationDefaults::forMode('generic')` |
| 15 | `zone.process_calibration.solution_fill` | zone | 1 | ✓ | `ZoneProcessCalibrationDefaults::forMode('solution_fill')` |
| 16 | `zone.process_calibration.tank_recirc` | zone | 1 | ✓ | `ZoneProcessCalibrationDefaults::forMode('tank_recirc')` |
| 17 | `zone.process_calibration.irrigation` | zone | 1 | ✓ | `ZoneProcessCalibrationDefaults::forMode('irrigation')` |
| 18 | `cycle.start_snapshot` | grow_cycle | 1 | — | `{}` |
| 19 | `cycle.phase_overrides` | grow_cycle | 1 | — | `{}` |
| 20 | `cycle.manual_overrides` | grow_cycle | 1 | — | `[]` |

**Scope: Phase 1 schema coverage** = namespaces 9-12, 14-17 (живая runtime-логика) + recipe phase payload (отдельный schema — см. §7).
Namespaces 1-7 (system) — реже меняются, Phase 1 опционально, Phase 2+ обязательно.
Namespace 13 (`zone.runtime_tuning_bundle`) — application-layer preset, не runtime. Не в scope рефакторинга.

---

## 2. `zone.correction` — полный inventory

Источник: [ZoneCorrectionConfigCatalog.php::defaults()](backend/laravel/app/Services/ZoneCorrectionConfigCatalog.php#L15-L112)

### 2.1 `controllers.ph.*`

| Path | Type | Default | Bounds | Required | Description |
|---|---|---|---|---|---|
| `controllers.ph.mode` | enum | `cross_coupled_pi_d` | `['cross_coupled_pi_d']` | ✓ | Тип алгоритма pH-контроллера |
| `controllers.ph.kp` | float | 0.28 | [0.0, 1000.0] | ✓ | PID proportional |
| `controllers.ph.ki` | float | 0.015 | [0.0, 100.0] | ✓ | PID integral |
| `controllers.ph.kd` | float | 0.0 | [0.0, 100.0] | ✓ | PID derivative |
| `controllers.ph.derivative_filter_alpha` | float | 0.35 | [0.0, 1.0] | ✓ | α для сглаживания derivative |
| `controllers.ph.deadband` | float | 0.04 | [0.0, 2.0] | ✓ | Зона без коррекции |
| `controllers.ph.max_dose_ml` | float | 35.0 | [0.001, 1000.0] | ✓ | Макс. разовая pH-доза |
| `controllers.ph.min_interval_sec` | int | 20 | [1, 3600] | ✓ | Мин. интервал между pH-дозами |
| `controllers.ph.max_integral` | float | 12.0 | [0.001, 500.0] | ✓ | Anti-windup cap |
| `controllers.ph.anti_windup.enabled` | bool | true | — | ✓ | Включить anti-windup |
| `controllers.ph.overshoot_guard.enabled` | bool | true | — | ✓ | Включить hard-limit guard |
| `controllers.ph.overshoot_guard.hard_min` | float | 4.0 | [0.0, 14.0] | ✓ | Нижний аварийный pH |
| `controllers.ph.overshoot_guard.hard_max` | float | 9.0 | [0.0, 14.0] | ✓ | Верхний аварийный pH |
| `controllers.ph.no_effect.enabled` | bool | true | — | ✓ | Контроль эффекта |
| `controllers.ph.no_effect.max_count` | int | 4 | [1, 10] | ✓ | Счётчик no-effect до alert |
| `controllers.ph.observe.telemetry_period_sec` | int | 2 | [1, 300] | ✓ | Ожидаемый период telemetry |
| `controllers.ph.observe.window_min_samples` | int | 3 | [2, 64] | ✓ | Мин. samples в окне |
| `controllers.ph.observe.decision_window_sec` | int | 8 | [1, 3600] | ✓ | Длина observe-окна |
| `controllers.ph.observe.observe_poll_sec` | int | 2 | [1, 300] | ✓ | Интервал observe-check |
| `controllers.ph.observe.min_effect_fraction` | float | 0.15 | [0.01, 1.0] | ✓ | Мин. доля эффекта |
| `controllers.ph.observe.stability_max_slope` | float | 0.04 | [0.0001, 100.0] | ✓ | Макс. slope стабильности |
| `controllers.ph.observe.no_effect_consecutive_limit` | int | 4 | [1, 10] | ✓ | Лимит no-effect до fail-closed |

### 2.2 `controllers.ec.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `controllers.ec.mode` | enum | `supervisory_allocator` | `['supervisory_allocator']` | ✓ |
| `controllers.ec.kp` | float | 0.55 | [0.0, 1000.0] | ✓ |
| `controllers.ec.ki` | float | 0.03 | [0.0, 100.0] | ✓ |
| `controllers.ec.kd` | float | 0.0 | [0.0, 100.0] | ✓ |
| `controllers.ec.derivative_filter_alpha` | float | 0.35 | [0.0, 1.0] | ✓ |
| `controllers.ec.deadband` | float | 0.06 | [0.0, 5.0] | ✓ |
| `controllers.ec.max_dose_ml` | float | 80.0 | [0.001, 1000.0] | ✓ |
| `controllers.ec.min_interval_sec` | int | 25 | [1, 3600] | ✓ |
| `controllers.ec.max_integral` | float | 20.0 | [0.001, 500.0] | ✓ |
| `controllers.ec.anti_windup.enabled` | bool | true | — | ✓ |
| `controllers.ec.overshoot_guard.enabled` | bool | true | — | ✓ |
| `controllers.ec.overshoot_guard.hard_min` | float | 0.0 | [0.0, 20.0] | ✓ |
| `controllers.ec.overshoot_guard.hard_max` | float | 10.0 | [0.0, 20.0] | ✓ |
| `controllers.ec.no_effect.enabled` | bool | true | — | ✓ |
| `controllers.ec.no_effect.max_count` | int | 4 | [1, 10] | ✓ |
| `controllers.ec.observe.*` | идентично ph.observe | — | — | ✓ |

### 2.3 `runtime.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `runtime.required_node_type` | string | `irrig` | max_length: 64 | ✓ |
| `runtime.clean_fill_timeout_sec` | int | 1200 | [30, 86400] | ✓ |
| `runtime.solution_fill_timeout_sec` | int | 900 | [30, 86400] | ✓ |
| `runtime.clean_fill_retry_cycles` | int | 1 | [0, 20] | ✓ |
| `runtime.level_switch_on_threshold` | float | 0.5 | [0.0, 1.0] | ✓ |
| `runtime.clean_max_sensor_label` | string | `level_clean_max` | max_length: 128 | ✓ |
| `runtime.clean_min_sensor_label` | string | `level_clean_min` | max_length: 128 | ✓ |
| `runtime.solution_max_sensor_label` | string | `level_solution_max` | max_length: 128 | ✓ |
| `runtime.solution_min_sensor_label` | string | `level_solution_min` | max_length: 128 | ✓ |

### 2.4 `timing.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `timing.sensor_mode_stabilization_time_sec` | int | 8 | [0, 3600] | ✓ |
| `timing.stabilization_sec` | int | 8 | [0, 3600] | ✓ |
| `timing.telemetry_max_age_sec` | int | 10 | [5, 3600] | ✓ |
| `timing.irr_state_max_age_sec` | int | 30 | [5, 3600] | ✓ |
| `timing.level_poll_interval_sec` | int | 10 | [5, 3600] | ✓ |

### 2.5 `dosing.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `dosing.solution_volume_l` | float | 100.0 | [1.0, 10000.0] | ✓ |
| `dosing.dose_ec_channel` | string | `pump_a` | max_length: 64 | ✓ |
| `dosing.dose_ph_up_channel` | string | `pump_base` | max_length: 64 | ✓ |
| `dosing.dose_ph_down_channel` | string | `pump_acid` | max_length: 64 | ✓ |
| `dosing.max_ec_dose_ml` | float | 80.0 | [0.1, 1000.0] | ✓ |
| `dosing.max_ph_dose_ml` | float | 35.0 | [0.1, 1000.0] | ✓ |

### 2.6 `retry.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `retry.max_ec_correction_attempts` | int | 8 | [1, 500] | ✓ |
| `retry.max_ph_correction_attempts` | int | 8 | [1, 500] | ✓ |
| `retry.prepare_recirculation_timeout_sec` | int | 900 | [30, 7200] | ✓ |
| `retry.prepare_recirculation_correction_slack_sec` | int | 0 | [0, 7200] | ✓ |
| `retry.prepare_recirculation_max_attempts` | int | 4 | [1, 10] | ✓ |
| `retry.prepare_recirculation_max_correction_attempts` | int | 40 | [1, 500] | ✓ |
| `retry.telemetry_stale_retry_sec` | int | 30 | [1, 3600] | ✓ |
| `retry.decision_window_retry_sec` | int | 10 | [1, 3600] | ✓ |
| `retry.low_water_retry_sec` | int | 60 | [1, 3600] | ✓ |

### 2.7 `tolerance.*`, `safety.*`

| Path | Type | Default | Bounds | Required |
|---|---|---|---|---|
| `tolerance.prepare_tolerance.ph_pct` | float | 5.0 | [0.1, 100.0] | ✓ |
| `tolerance.prepare_tolerance.ec_pct` | float | 10.0 | [0.1, 100.0] | ✓ |
| `safety.safe_mode_on_no_effect` | bool | true | — | ✓ |
| `safety.block_on_active_no_effect_alert` | bool | true | — | ✓ |

### 2.8 Phase overrides (`phases.*`)

`zone.correction` позволяет phase-level переопределения (см. `PHASES = ['solution_fill', 'tank_recirc', 'irrigation']`). Структура каждой фазы — **subset** от базового (любые поля из §2.1-2.7 могут быть переопределены per phase).

Compile order (Python [two_tank_runtime_spec.py:104-106](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L104-L106)):
```
solution_fill_cfg = merge(base, phases.solution_fill)
tank_recirc_cfg   = merge(base, phases.tank_recirc)
irrigation_cfg    = merge(base, phases.irrigation)
```

---

## 3. `zone.pid.ph` / `zone.pid.ec`

Источник: `ZonePidDefaults::forType()` (validation в Registry).

| Path | Type | Default (ph) | Default (ec) | Required | Constraint |
|---|---|---|---|---|---|
| `dead_zone` | float | 0.04 | 0.06 | ✓ | > 0 |
| `close_zone` | float | 0.18 | 0.25 | ✓ | > dead_zone |
| `far_zone` | float | 0.65 | 0.9 | ✓ | > close_zone |
| `zone_coeffs.close.kp` | float | 0.18 | 0.35 | ✓ | ≥ 0 |
| `zone_coeffs.close.ki` | float | 0.01 | 0.02 | ✓ | ≥ 0 |
| `zone_coeffs.close.kd` | float | 0.0 | 0.0 | ✓ | ≥ 0 |
| `zone_coeffs.far.kp` | float | 0.28 | 0.55 | ✓ | ≥ 0 |
| `zone_coeffs.far.ki` | float | 0.015 | 0.03 | ✓ | ≥ 0 |
| `zone_coeffs.far.kd` | float | 0.0 | 0.0 | ✓ | ≥ 0 |
| `max_integral` | float | 12.0 | 20.0 | ✓ | > 0 |

---

## 4. `zone.process_calibration.{generic,solution_fill,tank_recirc,irrigation}`

Источник: `ZoneProcessCalibrationDefaults::forMode()`.

| Path | Type | generic | solution_fill | tank_recirc | irrigation | Required |
|---|---|---|---|---|---|---|
| `ec_gain_per_ml` | float | 0.006 | 0.0016 | 0.010 | 0.008 | ✓ |
| `ph_up_gain_per_ml` | float | 0.015 | 0.004 | 0.022 | 0.018 | ✓ |
| `ph_down_gain_per_ml` | float | 0.015 | 0.004 | 0.022 | 0.018 | ✓ |
| `ph_per_ec_ml` | float | -0.002 | -0.002 | -0.002 | -0.002 | ✓ |
| `ec_per_ph_ml` | float | 0.001 | 0.001 | 0.001 | 0.001 | ✓ |
| `transport_delay_sec` | int | 4 | 4 | 4 | 4 | ✓ |
| `settle_sec` | int | 12 | 12 | 12 | 12 | ✓ |
| `confidence` | float | 0.85 | 0.85 | 0.85 | 0.85 | ✓ |
| `mode` | enum | — | — | — | — | ✓ |
| `source` | string | `system_default` | — | — | — | ✓ |
| `meta` | object | `{}` | — | — | — | — |

Validation: **хотя бы одно** из `{ec_gain_per_ml, ph_up_gain_per_ml, ph_down_gain_per_ml}` должно быть non-null numeric.

---

## 5. `zone.logic_profile` / `greenhouse.logic_profile`

| Path | Type | Default | Required | Notes |
|---|---|---|---|---|
| `active_mode` | string \| null | null | — | `greenhouse`: `['setup', 'working']`; `zone`: из `ZoneLogicProfileCatalog::allowedModes()` |
| `profiles` | object | `{}` | ✓ | map: mode → profile config |
| `profiles.*.subsystems.climate` | object | `{}` | ✓ (greenhouse) | не может содержать `targets` |
| `profiles.*.subsystems.climate.execution` | object | `{}` | ✓ (greenhouse) | |

Детальная структура `profiles.*.subsystems.irrigation.*` для zone — out of scope (живёт в `zone.logic_profile`, но runtime читает через `zone.correction` merge + recipe payload).

---

## 6. Compile pipeline (system → zone → cycle)

Источник: [AutomationConfigCompiler.php](backend/laravel/app/Services/AutomationConfigCompiler.php)

### 6.1 Последовательность

```
1. compileSystemBundle()     → читает 7 system.* documents → automation_effective_bundles(scope='system', id=0)
2. compileZoneBundle(zid)    → читает system bundle + zone.* documents → automation_effective_bundles(scope='zone', id=zid)
3. compileGrowCycleBundle(cid) → читает zone bundle + cycle.* + recipe phase → automation_effective_bundles(scope='grow_cycle', id=cid)
                              → сохраняет bundle_revision в grow_cycles.settings.bundle_revision
```

### 6.2 Bundle shape

```json
{
  "schema_version": 1,
  "system": { /* 7 namespaces */ },
  "zone": {
    "logic_profile": {...},
    "correction": {...},
    "pid": {"ph": {...}, "ec": {...}},
    "process_calibration": {"generic": {...}, "solution_fill": {...}, ...}
  },
  "cycle": {
    "start_snapshot": {...},
    "phase_overrides": {...},
    "manual_overrides": [...],
    "nutrition": {...}  // injected from recipe
  }
}
```

### 6.3 Bundle revision

Формула: `SHA1(config_json + '|' + violations_json)`
[AutomationConfigCompiler.php:186](backend/laravel/app/Services/AutomationConfigCompiler.php#L186)

- Не monotonic — меняется и при исправлении violations без изменения config
- Cycle snapshot pointer: `grow_cycles.settings.bundle_revision`
- AE3 читает текущий bundle по `bundle_revision` (immutable snapshot at cycle start)

### 6.4 Recompile triggers

Записи, которые триггерят cascade:

| Action | Trigger | Cascade |
|---|---|---|
| `upsertDocument(system.*, ...)` | `compileAffectedScopes('system', 0)` | system → all zones → all active cycles |
| `upsertDocument(zone.*, zid, ...)` | `compileAffectedScopes('zone', zid)` | zone → active cycles этой зоны |
| `upsertDocument(cycle.*, cid, ...)` | `compileAffectedScopes('grow_cycle', cid)` | только этот cycle |
| `upsertRuntimeTuningBundle(zid, ...)` | атомарный upsert 7 docs + `compileZoneBundle(zid)` | zone (без cycle cascade — намеренно?) |

### 6.5 Violations

Источник: [AutomationConfigCompiler.php:238-271](backend/laravel/app/Services/AutomationConfigCompiler.php#L238-L271)

| Code | Namespace | Path | Severity | Blocking |
|---|---|---|---|---|
| `missing_active_logic_profile` | `zone.logic_profile` | `active_mode` | error | ✓ |
| `missing_cycle_start_snapshot` | `cycle.start_snapshot` | (root) | error | ✓ |

**Pattern**: compiler пишет в `automation_config_violations`, при наличии blocking → bundle.status='invalid'. AE3 не должен запускать task для invalid bundle (validation в AE3 пока отсутствует — **добавить в Phase 2**).

---

## 7. Recipe phase payload

Источник: активный recipe phase через `grow_cycles.currentPhase` relation.

**Не является отдельным namespace** в automation_config_documents, но AE3 использует через `snapshot.phase_targets`, `snapshot.targets`, `snapshot.diagnostics_execution` — это payload recipe phase активного цикла.

Ключевые поля (читаются в two_tank_runtime_spec.py:171-175):

| Path | Type | Required | Source |
|---|---|---|---|
| `phase_targets.ph.target` | float [0.0, 14.0] | ✓ | recipe phase |
| `phase_targets.ph.min` | float [0.0, 14.0] | — (fallback на target) | recipe phase |
| `phase_targets.ph.max` | float [0.0, 14.0] | — (fallback на target) | recipe phase |
| `phase_targets.ec.target` | float [0.0, 20.0] | ✓ | recipe phase |
| `phase_targets.ec.min` | float [0.0, 20.0] | — (fallback) | recipe phase |
| `phase_targets.ec.max` | float [0.0, 20.0] | — (fallback) | recipe phase |
| `phase_targets.day_night_enabled` | bool | — | recipe phase |
| `phase_targets.extensions.day_night` | object | — | recipe phase |
| `phase_targets.ec_component_ratios.npk_ec_share` | float | — (fallback 1.0 ⚠️) | recipe phase |
| `targets.irrigation.*` | object | — (может быть пусто) | recipe phase |
| `targets.extensions.subsystems.irrigation.*` | object | — | recipe phase |
| `diagnostics_execution.two_tank_commands` | object | — | recipe phase |
| `diagnostics_execution.fail_safe_guards` | object | — (fallback на Python defaults ⚠️) | recipe phase |
| `diagnostics_execution.startup.irr_state_wait_timeout_sec` | float | — (fallback 5.0 ⚠️) | recipe phase |

**Recipe phase = отдельный JSON Schema** (`schemas/recipe_phase.v1.json` в Phase 1). По Q4 решению — live mode должен покрывать hot-reload recipe phase.

---

## 8. AE3 Python resolver (`two_tank_runtime_spec.py`)

Файл: [backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py) (1157 строк)

### 8.1 Публичный API

```python
def resolve_two_tank_runtime(snapshot: Any) -> dict[str, Any]: ...  # line 84
def default_two_tank_command_plan(plan_name: str) -> list[dict]: ... # line 28
```

### 8.2 Topology requirements

`_REQUIRED_TWO_TANK_PLAN_CHANNELS` ([line 14-25](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L14-L25)):
```python
{
    "irrigation_start":           ("valve_solution_supply", "valve_irrigation", "pump_main"),
    "irrigation_stop":            ("pump_main", "valve_irrigation", "valve_solution_supply"),
    "clean_fill_start":           ("valve_clean_fill",),
    "clean_fill_stop":            ("valve_clean_fill",),
    "solution_fill_start":        ("valve_clean_supply", "valve_solution_fill", "pump_main"),
    "solution_fill_stop":         ("pump_main", "valve_solution_fill", "valve_clean_supply"),
    "prepare_recirculation_start":("valve_solution_supply", "valve_solution_fill", "pump_main"),
    "prepare_recirculation_stop": ("pump_main", "valve_solution_fill", "valve_solution_supply"),
    "irrigation_recovery_start":  ("valve_irrigation", "valve_solution_supply", "valve_solution_fill", "pump_main"),
    "irrigation_recovery_stop":   ("pump_main", "valve_solution_fill", "valve_solution_supply", "valve_irrigation"),
}
```

**В Phase 1 schema:** описать это как `$defs/two_tank_command_channels` с enum валидацией. Топология two_tank hardcoded в коде — допустимо, т.к. другие топологии пока не поддерживаются.

### 8.3 Python-side hardcoded defaults (должны исчезнуть после Phase 3-4)

| Константа / fallback | Значение | Line | Должно стать |
|---|---|---|---|
| `_DEFAULT_PREPARE_RECIRC_MAX_CORRECTION_ATTEMPTS` | 20 | 12 | Required в schema (уже есть в PHP catalog как `retry.prepare_recirculation_max_correction_attempts` default 40, но fallback 20 если не указано) ⚠ mismatch |
| `_MAX_CORRECTION_ATTEMPTS` | 500 | 13 | Safety cap — оставить как JSON Schema `maximum` |
| `irr_state_wait_timeout_sec` fallback | 5.0 | 227 | Required в `recipe_phase.diagnostics_execution.startup` |
| `prepare_recirculation_correction_slack_sec` fallback | 900 | 197 | PHP default = 0, Python default = 900 ⚠ **mismatch** |
| `irrigation.correction_slack_sec` fallback | 900 | 868-871 | Required в `recipe_phase.targets.irrigation` |
| `irrigation.stage_timeout_sec` fallback | 3600 | 875 | Required в `recipe_phase.targets.irrigation` |
| `irrigation_recovery.max_continue_attempts` | 5 | 940 | Required в recipe |
| `irrigation_recovery.timeout_sec` | 600 | 941 | Required в recipe |
| `irrigation_recovery.max_replays` | 1 | 943 | Required в recipe |
| `fail_safe_guards.clean_fill_min_check_delay_ms` | 5000 | 950-975 | Required в `recipe_phase.diagnostics_execution.fail_safe_guards` |
| `fail_safe_guards.solution_fill_min_check_delay_ms` | 5000 | — | Required |
| `fail_safe_guards.solution_fill_max_check_delay_ms` | 15000 | — | Required |
| `fail_safe_guards.estop_debounce_ms` | 80 | — | Required |
| `ec_dosing_mode` fallback | `single` | 1129 | Required в `zone.correction.dosing` (поле отсутствует в PHP catalog ⚠ **gap**) |
| `correction_during_irrigation` fallback | true | 860 | Required в `recipe_phase.targets.irrigation` |
| `npk_ec_share` fallback | 1.0 | 609, 277 | Required в `recipe_phase.phase_targets.ec_component_ratios` (fallback допустим для single-component) |

### 8.4 Handler-level hardcoded defaults

| Файл | Константа | Значение | Line |
|---|---|---|---|
| `handlers/clean_fill.py` | `_STALE_RECHECK_DELAY_SEC` | 0.25 | 27 |
| `handlers/clean_fill.py` | `_SOURCE_EMPTY_RETRY_CYCLES` | 2 | 28 |
| `handlers/solution_fill.py` | `_STALE_RECHECK_DELAY_SEC` | 0.25 | 31 |
| `handlers/irrigation_check.py` | `_STALE_RECHECK_DELAY_SEC` | 0.25 | 29 |
| `handlers/correction.py:690,781,810,1939` | retry delays fallback | 30.0 / 60.0 | — |
| `handlers/correction.py:803` | stale_recheck | 0.25 | — |
| `handlers/prepare_recirc_window.py` | `_DEFAULT_PREPARE_RECIRCULATION_MAX_ATTEMPTS` | 3 | 22 |
| `handlers/base.py` | `_IRR_STATE_PROBE_RETRY_COUNT` | 1 | — |
| `handlers/base.py` | `_IRR_STATE_PROBE_RETRY_DELAY_SEC` | 0.5 | — |
| `handlers/base.py` | `_IRR_PROBE_FAILURE_STREAK_LIMIT` | 5 | — |
| `handlers/base.py` | `_IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC` | 30.0 | — |
| `domain/services/correction_planner.py` | `_DEFAULT_SOLUTION_VOLUME_L` | 100.0 | 19 |
| `domain/services/correction_planner.py` | `_DEFAULT_MAX_EC_DOSE_ML` | 50.0 | 22 |
| `domain/services/correction_planner.py` | `_DEFAULT_MAX_PH_DOSE_ML` | 20.0 | 25 |
| `runtime/bootstrap.py:73` | `httpx.AsyncClient(timeout=10.0)` | 10.0 | 73 |

### 8.5 Runtime dict shape (что handler-ы читают)

~50 top-level полей, все `Required` для корректного execution. Для полного списка см. §D в agent report (выше) или [two_tank_runtime_spec.py:176-300](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L176-L300).

Ключевые группы:
- **Timeouts/thresholds** — `clean_fill_timeout_sec`, `solution_fill_timeout_sec`, `prepare_recirculation_timeout_sec`, `level_switch_on_threshold`, `telemetry_max_age_sec`
- **Targets (читаются из recipe phase)** — `target_ph`, `target_ec`, `target_ph_{min,max}`, `target_ec_{min,max}`, `target_ec_prepare*`
- **Sensor labels** — `{clean,solution}_{max,min}_sensor_labels` (plural, **двойное имя** — см. §9.1)
- **Correction configs** — `correction` (default), `correction_by_phase` (4 ключа: `solution_fill`, `tank_recirc`, `irrigation`, `generic`)
- **Command specs** — `command_specs` (merged с default channels)
- **Fail-safe guards** — `fail_safe_guards`
- **Irrigation** — `irrigation_execution`, `irrigation_decision`, `irrigation_recovery`, `irrigation_safety`, `soil_moisture_target`
- **PID state** — `pid_state`, `pid_configs`, `process_calibrations`

---

## 9. Undocumented behaviors и design decisions для Phase 3

Найденные при аудите weird behaviors, которые требуют явного решения при рефакторинге. **Флаг `[D]`** = решение нужно от пользователя перед Phase 3 handler migration.

### 9.1 `[D]` Double-naming plural/singular

[two_tank_runtime_spec.py:163-165](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L163) (и ещё 3 места):

```python
_first_non_null(
    fill_runtime_cfg.get("clean_max_sensor_labels"),  # plural
    fill_runtime_cfg.get("clean_max_sensor_label"),   # singular
)
```

PHP catalog использует singular. Python поддерживает оба (plural → array, singular → single string). **Legacy backward compat**, вероятно для перехода на multi-sensor sensing.

**Решение для Phase 3**: в новой JSON Schema оставляем только **plural** (`clean_max_sensor_labels: array`). Singular удаляется. Existing zones с singular fail validation → нужна миграция данных в PHP.

### 9.2 `[D]` EC share fallback 1.0 (single-tank compat)

[line 277](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L277), [line 609](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L609):

Если `ec_component_ratios.npk_ec_share` отсутствует → `npk_ec_share = 1.0`, т.е. весь EC идёт в prepare. Это режим "один бак = один компонент раствора". Технически backward compat для single-tank зон, которые не имеют разделения NPK/A/B.

**Решение**: оставить fallback 1.0 **только если `ec_dosing_mode == 'single'`**. Для `multi_parallel` — required.

### 9.3 `[D]` Soil moisture dual path

[line 993-1035](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L993):

Читается из двух мест:
- `targets.extensions.subsystems.irrigation.targets.soil_moisture`
- `targets.extensions.day_night.soil_moisture`

**Решение**: канонический путь — `targets.extensions.subsystems.irrigation.targets.soil_moisture`. `day_night.soil_moisture` устарел, удалить из schema.

### 9.4 `[D]` Silent empty correction при missing process_calibrations

[line 479, 1127](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L479):

Если `process_calibrations` отсутствует → `pump_calibration = {}`. Controllers.* могут быть пусты. Корректор не работает, но task не падает.

**Решение**: required в schema. Если `process_calibrations` пустой → `ConfigValidationError`. Это уже покрывается required namespace `zone.process_calibration.*` на стороне Laravel, но Python этого не валидирует.

### 9.5 Mismatch Python vs PHP defaults

| Параметр | PHP default | Python fallback | Severity |
|---|---|---|---|
| `retry.prepare_recirculation_correction_slack_sec` | 0 | 900 | **high** (отличаются на 900 секунд) |
| `retry.prepare_recirculation_max_correction_attempts` | 40 | 20 | **medium** |
| `retry.prepare_recirculation_max_attempts` | 4 | 3 (в prepare_recirc_window.py) | low |

**Решение**: единственный источник — JSON Schema / PHP catalog (since PHP — authority). Python-defaults удалить, runtime читает из bundle.

### 9.6 Command plan timeout_ms injection (not a blocker)

[line 764-787](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L764):

Для `solution_fill_start` и `prepare_recirculation_start` автоматически инжектится `timeout_ms` в params `pump_main`. Это трансформация, происходящая в resolver.

**Решение**: оставить — это derived value, не config-параметр.

### 9.7 Hardcoded physical bounds pH=14, EC=20 (legitimate)

[line 703, 723](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L703):

Константы `14.0` (pH max) и `20.0` (EC max) — физические границы телеметрии. Легитимно как `maximum:` в JSON Schema.

**Решение**: оставить, вынести в `$defs/physics_bounds`.

### 9.8 `ec_dosing_mode` — gap в PHP catalog

Поле `dosing.ec_dosing_mode` используется в Python ([line 1129](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L1129)) с fallback `"single"`, но **отсутствует в `ZoneCorrectionConfigCatalog::defaults()`**. Возможно, приходит из `phases.*.dosing.ec_dosing_mode` или задаётся неявно через `ec_component_ratios`.

**Решение**: добавить поле `dosing.ec_dosing_mode: enum['single', 'multi_parallel']` в PHP catalog defaults (= 'single') + JSON Schema required. Это **небольшое изменение PHP** в Phase 1.

### 9.9 Post-build validation (not a blocker)

[line 473-494, 302](backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py#L473):

Валидация `prepare_recirculation_timeout_sec < stabilization_sec + observe_window_sec` проверяется **после** построения runtime, а не в schema.

**Решение**: добавить `dependencies` / `if-then` constraint в JSON Schema 2020-12. Если не выразимо — оставить Python-валидацию как post-load check в `config/loader.py`.

---

## 10. Executor-specific summary для Phase 1

### 10.1 Scope первой JSON Schema (`schemas/zone_correction.v1.json`)

Все поля из §2 (48 параметров). Приоритет:
1. Корень: `{controllers, runtime, timing, dosing, retry, tolerance, safety}`
2. Phases override: `{phases: {solution_fill: <subset>, tank_recirc: <subset>, irrigation: <subset>}}`
3. `$defs` для переиспользования: `Seconds`, `Milliliters`, `Percent`, `PositiveCount`, `ControllerConfig`, `ObserveConfig`
4. `additionalProperties: false` на всех уровнях
5. **+ новое поле** `dosing.ec_dosing_mode: enum['single', 'multi_parallel']` с default `'single'` (Phase 1 action)

### 10.2 Scope второй JSON Schema (`schemas/recipe_phase.v1.json`)

Из §7:
- `phase_targets.{ph,ec}.{target, min, max}` + `ec_component_ratios`
- `targets.irrigation.*` (decision, recovery, safety, correction_slack_sec, stage_timeout_sec, correction_during_irrigation)
- `diagnostics_execution.{two_tank_commands, fail_safe_guards, startup.irr_state_wait_timeout_sec}`
- `day_night.*`

### 10.3 Прочие schemas (опционально в Phase 1)

- `schemas/zone_pid.v1.json` — для `zone.pid.{ph,ec}` (§3)
- `schemas/zone_process_calibration.v1.json` — для `zone.process_calibration.*` (§4)
- `schemas/zone_logic_profile.v1.json` — упрощённо (§5)
- `schemas/system_automation_defaults.v1.json` — для `system.*` (позже)

### 10.4 Ключевые заметки для executor

1. **Numeric literals bound** — всегда одинаковые для controllers.ph и controllers.ec, но hard_min/max разные (`[0,14]` vs `[0,20]`).
2. **`$ref` к `$defs`** — использовать для всех повторяющихся структур (observe, overshoot_guard, anti_windup, no_effect).
3. **`required` arrays** — все поля из §2 в required, для `phases.*` — **пустой required** (субсет, всё опционально).
4. **`additionalProperties: false`** — строго, но в `phases.*` оставить true, потому что не все поля туда попадают.
5. **Version tagging** — в JSON Schema `$id: "https://hydro2.local/schemas/zone_correction/v1.json"` + `schema_version: const=1` для sanity check.

---

## 11. Decisions needed before Phase 3 (не blocking для Phase 1)

Эти решения нужны **перед Phase 3** (handler migration), но не блокируют Phase 1 (JSON Schema extraction).

| # | Decision | Вариант A | Вариант B | Рекомендация |
|---|---|---|---|---|
| D1 | Plural vs singular sensor labels (§9.1) | только plural, миграция | поддерживать оба | A (миграция при upsertDocument) |
| D2 | EC share 1.0 fallback (§9.2) | условный fallback (только single) | strict required | A |
| D3 | Soil moisture path (§9.3) | только `subsystems.irrigation.targets` | поддерживать оба | A |
| D4 | Silent empty correction (§9.4) | loud fail | silent | A |
| D5 | Python defaults mismatch (§9.5) | удалить Python, PHP authority | reconcile, выбрать «правильные» | A, но требует подтверждения значений |
| D6 | `ec_dosing_mode` в PHP catalog (§9.8) | добавить с default 'single' | оставить implicit | A (микро-change в Phase 1) |

**Предлагаемая процедура**: зафиксировать D1-D6 при старте Phase 3 одним ack от пользователя. До тех пор — Phase 1/2 не блокируются.

---

## 12. Метрики аудита

| Метрика | Значение |
|---|---|
| Namespaces в scope рефакторинга | 10 из 20 |
| Параметров в `zone.correction` | 48 |
| Phase override scope | 3 phases × 48 = 144 override slots |
| Python hardcoded defaults в resolver | 17 |
| Python hardcoded defaults в handlers | 12 |
| Python hardcoded defaults в planner | 3 |
| Runtime dict top-level keys | ~50 |
| PHP default source files | 4 (Catalog, ZonePidDefaults, ZoneProcessCalibrationDefaults, SystemAutomationSettingsCatalog) |
| Mismatched defaults (PHP vs Python) | 3 обнаружено (§9.5) |
| Weird/undocumented behaviors | 8 (§9) |
| Design decisions для Phase 3 | 6 (§11) |

---

## 13. Связанные документы

- [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md) — основной план
- [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) — текущий AUTHORITY
- [ae3lite.md](ae3lite.md) — runtime doc
- [AE3_RUNTIME_EVENT_CONTRACT.md](AE3_RUNTIME_EVENT_CONTRACT.md) — событийный контракт
