# AE3 Canonicalization Plan

**Ветка:** `ae3`  
**Статус:** Завершён (2026-04-18)
**См. также:** [`backend/services/automation-engine/AE3_CONSISTENCY_TODO.md`](../../backend/services/automation-engine/AE3_CONSISTENCY_TODO.md) — post-canonicalization consistency audit (Batch A + Batch F, тоже завершён)
**Цель:** Убрать технический долг: мёртвый код, дублирование тестов, устаревший адаптер перевода JSONB-payload в типизированные данные.

---

## Контекст

`LegacyIntentMapper` — адаптер совместимости между Laravel scheduler и AE3-Lite v2.  
Laravel пишет строки в `zone_automation_intents.payload` (JSONB), Python разбирает этот JSON вручную.  
Обратная совместимость **не нужна** — проект в активной разработке, переключение чистое.

---

## Задачи

### ✅ Фаза 0 — Dead code audit (DONE, commit `177631f5`)

- Удалены `utils/adaptive_pid.py`, `config/settings.py`, `config/scheduler_task_mapping.py`
- Исправлен баг `_reset_pid_state_if_inside_bounds`
- Добавлена валидация `ml_per_sec`
- Вынесен `_normalize_phase_key` → `phase_utils.py`

---

### ✅ Фаза 1 — Типизированные колонки в `zone_automation_intents` (DONE)

**Миграция:** `2026_04_12_100000_add_typed_columns_to_zone_automation_intents.php`

Добавлены колонки:
- `task_type VARCHAR(64) DEFAULT 'cycle_start'` — `irrigation_start | cycle_start | lighting_tick`
- `topology VARCHAR(64) DEFAULT 'two_tank'` — `two_tank | two_tank_drip_substrate_trays | lighting_tick`
- `irrigation_mode VARCHAR(32) NULL` — `normal | force | NULL`
- `irrigation_requested_duration_sec INT UNSIGNED NULL`
- `intent_source VARCHAR(64) NULL` — `laravel_scheduler | api | laravel_grow_cycle_start`

`payload` оставлен как JSONB nullable — больше не записывается и не читается.

**Обновлённые PHP-файлы:**
- `ScheduleDispatcher.php::upsertSchedulerIntent()` — typed columns
- `ZoneAutomationIntentService.php::upsertStartIrrigationIntent()` — typed columns
- `GrowCycleService.php::upsertGrowCycleStartIntent()` — typed columns; `payload->>'workflow'` → `task_type`

---

### ✅ Фаза 2 — `PgZoneIntentRepository.extract_intent_metadata()` (DONE)

- `IntentMetadata` dataclass перенесён в `ae3lite/domain/intent_metadata.py`
- Метод `extract_intent_metadata()` добавлен в `PgZoneIntentRepository` — читает из typed columns
- 18 unit-тестов в `test_ae3lite_extract_intent_metadata.py`

---

### ✅ Фаза 3 — Удаление LegacyIntentMapper (DONE)

**Удалено:**
- `ae3lite/application/adapters/legacy_intent_mapper.py`
- `test_ae3lite_legacy_intent_mapper.py`

**Обновлено:**
- `create_task_from_intent.py` — `zone_intent_repository` вместо `legacy_intent_mapper`
- `bootstrap.py` — убран import `LegacyIntentMapper`, передаётся `zone_intent_repository`
- `ExecutionRunReadModel.php` — `intents.task_type` вместо `intents.payload`, убран `normalizeJson` для intent payload
- Все тесты `create_task_from_intent` (unit + integration) обновлены на typed columns

---

### ✅ Фаза 4 — Консолидация дублирующихся тест-файлов (DONE — N/A)

**Результат аудита:** дублирование фактически отсутствует.

| Файл | Строк | Тестов | Статус |
|------|-------|--------|--------|
| `test_ae3lite_correction_handler.py` | 2797 | 64 | единственный handler-тест, дубля нет |
| `test_ae3lite_handler_irrigation_check_correction.py` | 744 | 11 | уже консолидирован |
| `test_ae3lite_handler_prepare_recirc_check.py` | 649 | — | уже 2 файла (check + window) |
| `test_ae3lite_handler_prepare_recirc_window.py` | 284 | — | уже 2 файла (check + window) |

Старые дублирующие файлы (`test_ae3lite_irrigation_check_handler.py` и 4 файла prepare_recirc) были удалены ранее.

---

### ✅ Фаза 5 — DB constraints (DONE — реализовано ранее)

Все три constraint реализованы в миграции `2026_03_06_120000_create_ae3lite_v1_runtime_tables.php`:

| Constraint | Статус |
|---|---|
| `ae_tasks_active_zone_unique` partial unique index `WHERE status IN (...)` | ✅ |
| `zone_workflow_state.version BIGINT DEFAULT 0` | ✅ |
| `zones.automation_runtime VARCHAR(16) DEFAULT 'ae3'` + CHECK | ✅ (только `'ae3'`, ae2 runtime удалён) |

---

## Критерии готовности

- [x] `zone_automation_intents.payload` больше не записывается и не читается ни в одном месте
- [x] `LegacyIntentMapper` и его тест-файл удалены, никаких импортов не осталось
- [x] `IntentMetadata` живёт в доменном слое (`ae3lite/domain/intent_metadata.py`)
- [x] `CreateTaskFromIntentUseCase` принимает `zone_intent_repository`, не `legacy_intent_mapper`
- [x] Все 1057+ тестов automation-engine зелёные
- [x] Нет PHP кода, читающего `payload->>'*'` для маршрутизации (только `grow_cycle_id` fallback для legacy rows)
