# AE2-Lite Implementation Audit (2026-02-22)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Scope

Аудит выполнен по `doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md` (P0/P1 + CI smoke).

## P0 Status

1. AE2-Lite структура `ae2lite/`: **DONE**
- canonical каталог присутствует;
- добавлены недостающие файлы: `api_models.py`, `correction_controller.py`, `pid.py`, `gating.py`.

2. Ограничение размера AE Python файлов `< 400 LOC`: **DONE**
- активные файлы runtime соответствуют лимиту;
- legacy runtime-пакет `backend/services/automation-engine/legacy/` удален полностью;
- в `backend/services/automation-engine` нет Python-файлов `>= 400 LOC`.

3. DB индексы polling/freshness: **DONE**
- миграция: `backend/laravel/database/migrations/2026_02_22_120300_add_ae2_runtime_polling_indexes.php`
- индексы:
  - `commands_status_updated_at_idx`
  - `telemetry_last_sensor_updated_at_idx`

4. DATA_MODEL_REFERENCE обновлен: **DONE**
- `zone_automation_intents` + lifecycle;
- `command_plans` schema (`schema_version`, `plan_version`, `steps`);
- `NOTIFY` channels/triggers: `ae_command_status`, `ae_signal_update`;
- индексы polling/freshness задокументированы.

## Test/CI Status

- `tools/testing/check_ae2_invariants.sh`: **PASS**
- `docker compose ... automation-engine pytest -q`: **300 passed**
- `docker compose ... laravel php artisan test` (scheduler/control-mode/manual-step smoke): **21 passed**
- `backend/laravel/scripts/check-file-size-guard.sh`: **PASS**

## Изменения в CI guard

Обновлен file-size guard:
- script: `backend/laravel/scripts/check-file-size-guard.sh`
- временные исключения сняты; `backend/laravel/scripts/file-size-guard-exceptions.txt` удален из репозитория.

## Дополнительные исправления

- `backend/services/automation-engine/test_notify_partition_smoke.py`:
  добавлен корректный `skip`, если в тестовой БД отсутствует/не партиционирована таблица `commands`.
- API runtime переведен с `legacy/api_runtime.py` на canonical `ae2lite/api_runtime.py`:
  - `backend/services/automation-engine/api.py` -> `ae2lite.api_runtime`
  - `backend/services/automation-engine/ae2lite/api.py` -> `ae2lite.api_runtime`
- Main runtime переведен с `legacy/main_runtime.py` на canonical `ae2lite/main_runtime.py`:
  - `backend/services/automation-engine/ae2lite/main.py` -> `ae2lite.main_runtime`
  - runtime декомпозирован в модули:
    - `ae2lite/main_runtime_shared.py`
    - `ae2lite/main_runtime_ops.py`
    - `ae2lite/main_runtime_cycle.py`
    - `ae2lite/main_runtime_shutdown.py`
