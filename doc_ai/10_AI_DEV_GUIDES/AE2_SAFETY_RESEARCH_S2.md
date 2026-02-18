# AE2_SAFETY_RESEARCH_S2.md
# Mini-S2 research: safety bounds для correction path

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Точки внедрения (decision-complete)
1. `config/settings.py`:
- feature flags и safety defaults.

2. Новый policy:
- `services/correction_bounds_policy.py`:
  - `resolve_bounds(metric, targets, bounds_overrides, settings)`
  - `validate_target_with_bounds(...)`
  - `apply_target_rate_limit(...)`

3. `correction_controller.py`:
- применять bounds-policy до PID.
- fail-closed skip при unsafe/invalid bounds.
- clamp target при rate-limit.
- structured reason_code/event payload.

4. `services/zone_correction_orchestrator.py`:
- извлекать `bounds_overrides` в hybrid режиме.
- передавать `bounds_overrides` в `ph_controller` и `ec_controller`.

## 2. Hybrid reading strategy
Приоритет источников bounds:
1. `bounds_overrides` (runtime override, если присутствует).
2. `targets.<metric>` (`hard_pct`, `abs_min/abs_max`, `max_delta_per_min`, либо `bounds.*`).
3. safe defaults из `AutomationSettings`.

Поддерживаемые runtime paths для override extraction:
1. `targets.bounds`
2. `targets.execution.bounds`
3. `targets.diagnostics.execution.bounds`
4. `targets.extensions.safety.bounds`

## 3. Fail-closed правила
1. Если bounds неконсистентны (`abs_min > abs_max`) -> skip.
2. Если target выходит за `abs_min/abs_max` -> skip.
3. Если нарушен `hard_pct` относительно прошлого target (при наличии истории) -> skip.
4. Если kill-switch активен -> legacy behavior (без новых guard).

## 4. Риски и митигации
1. Риск ложных skip из-за неполных данных bounds.
- Митигация: fallback на defaults + structured audit.

2. Риск резких setpoint jumps.
- Митигация: `max_delta_per_min` clamp.

3. Риск regressions в existing correction flow.
- Митигация: unit + integration тесты и Docker smoke.

## 5. Проверочные сценарии (обязательные)
1. target вне `abs_min/abs_max`.
2. `hard_pct` violation при наличии previous target.
3. `max_delta_per_min` clamp.
4. priority override > targets > defaults.
5. kill-switch возвращает legacy path.
