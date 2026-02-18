# AE2_CORRECTION_POLICY_HARDENING_S9.md
# AE2 S9: Correction/Policy Hardening

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель S9
Закрыть Tier-1 часть policy hardening в `automation-engine`: proactive correction по тренду и anomaly-блок дозирования при повторяющемся `no_effect`.

## 2. Реализовано
1. Proactive correction (EWMA/slope):
- `backend/services/automation-engine/correction_cooldown.py`
  - добавлены:
    - `analyze_proactive_correction_signal(...)`
    - `should_apply_proactive_correction(...)`
  - логика:
    - EWMA по telemetry window;
    - slope per minute;
    - прогноз на horizon;
    - trigger если прогноз выводит метрику за dead-zone и тренд ухудшается.
- `backend/services/automation-engine/correction_controller.py`
  - внутри dead-zone добавлен proactive-путь;
  - при trigger создается `*_PROACTIVE_CORRECTION_TRIGGERED`;
  - payload команды помечается `proactive_mode=true` + диагностикой прогноза.

2. Equipment anomaly guard (`dose -> no_effect xN`):
- `backend/services/automation-engine/correction_controller.py`
  - добавлен runtime-state:
    - `_pending_effect_window_by_zone`
    - `_no_effect_streak_by_zone`
    - `_anomaly_blocked_until_by_zone`
  - после успешной коррекции регистрируется окно ожидания эффекта;
  - при истечении окна:
    - если эффект подтвержден -> `*_DOSE_EFFECT_CONFIRMED`;
    - если нет -> `*_DOSE_NO_EFFECT`, увеличение streak;
    - при `streak >= threshold` -> `*_DOSING_BLOCKED_ANOMALY` и infra-alert;
  - при активном block новые дозировки пропускаются с `*_CORRECTION_SKIPPED_ANOMALY` (`status=degraded`).

3. Новые настройки:
- `backend/services/automation-engine/config/settings.py`
  - proactive flags/defaults:
    - `AE_PROACTIVE_CORRECTION_ENABLED`
    - `AE_PROACTIVE_EWMA_ALPHA`
    - `AE_PROACTIVE_WINDOW_MINUTES`
    - `AE_PROACTIVE_HORIZON_MINUTES`
    - `AE_PROACTIVE_MIN_POINTS`
    - `AE_PROACTIVE_PH_MIN_SLOPE_PER_MIN`
    - `AE_PROACTIVE_EC_MIN_SLOPE_PER_MIN`
  - anomaly flags/defaults:
    - `AE_EQUIPMENT_ANOMALY_GUARD_ENABLED`
    - `AE_EQUIPMENT_ANOMALY_NO_EFFECT_WINDOW_SEC`
    - `AE_EQUIPMENT_ANOMALY_STREAK_THRESHOLD`
    - `AE_EQUIPMENT_ANOMALY_BLOCK_MINUTES`
    - `AE_EQUIPMENT_ANOMALY_PH_MIN_DELTA`
    - `AE_EQUIPMENT_ANOMALY_EC_MIN_DELTA`

## 3. Что не менялось
1. Путь публикации команд не менялся (`CommandGateway`/`CommandBus` path сохранен).
2. MQTT/REST/DB внешние контракты не менялись.
3. Scheduler baseline-поведение и security baseline не менялись.

## 4. Regression тесты
1. `pytest -q test_correction_cooldown.py test_correction_controller.py test_config_settings.py` -> `73 passed`.
2. `pytest -q test_zone_automation_service.py` -> `45 passed`.

## 5. Остаточные задачи перед S10
1. Вынести anomaly/proactive runtime-state в единый serialize/restore контракт (S10 crash-recovery scope).
2. Добавить cross-process persistency для pending-window/no-effect-streak при рестарте сервиса.
3. Свести policy/decision state-machine в отдельный модуль с явными transition-тестами.
