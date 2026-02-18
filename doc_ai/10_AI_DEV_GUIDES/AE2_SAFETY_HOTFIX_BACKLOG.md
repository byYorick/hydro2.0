# AE2_SAFETY_HOTFIX_BACKLOG.md
# AE2 Safety Hotfix Backlog (S3-first)

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Приоритизация

### P0 (обязательные в текущем цикле)
1. Ввести fail-closed safety bounds для pH/EC в correction path:
- `hard_pct`
- `abs_min/abs_max`
- `max_delta_per_min`

2. Добавить kill-switch для быстрых rollback без отката кода:
- `AE_SAFETY_BOUNDS_ENABLED`
- `AE_SAFETY_BOUNDS_KILL_SWITCH`

3. Добавить структурные audit reason_code для skip/clamp решений.

### P1 (после P0)
1. Расширить integration tests на propagation bounds overrides через orchestrator.
2. Добавить shadow-метрики частоты safety skip/clamp решений.

### P2 (следующие stage)
1. Расширить bounds на другие контроллеры (climate/irrigation) при наличии контракта.
2. Формализовать alert thresholds для новых safety reason_code.

## Нельзя делать в hotfix треке
1. Не менять publish pipeline команд.
2. Не внедрять новые MQTT контракты.
3. Не вводить DB schema изменения для S3.
