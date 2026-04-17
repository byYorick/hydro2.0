# AUTOMATION_CONFIG_AUTHORITY.md
# Единый authority automation/runtime-конфигов

**Версия:** 1.3  
**Дата обновления:** 2026-04-17  
**Статус:** Канонично для Laravel runtime, AE3 read-model и web-admin (+ §6.4 config modes Phase 5; автогенерируемые таблицы обновляются `python3 tools/generate_authority.py`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: прежние automation config endpoints, Inertia authority props и старые authority-таблицы не входят в runtime read-path; обратная совместимость не поддерживается.

---

## 1. Назначение

Документ фиксирует новую каноническую модель automation/runtime-конфигов:

- один authority для backend/runtime;
- один schema-first registry;
- один compiler pipeline;
- один runtime read-path через compiled bundles;
- один frontend read/write path через unified automation config API.

Вне scope:

- `NodeConfig`, `config_report`, firmware NVS;
- ingestion конфигов нод;
- мобильный клиент.

Эти контуры остаются отдельными системами и не входят в automation authority.

---

## 2. Границы authority

### 2.1 Что входит в authority

Authority покрывает только automation/runtime-конфиги:

- `system.runtime`
- `system.automation_defaults`
- `system.command_templates`
- `system.process_calibration_defaults`
- `system.pump_calibration_policy`
- `system.sensor_calibration_policy`
- `greenhouse.logic_profile`
- `zone.logic_profile`
- `zone.correction`
- `zone.pid.ph`
- `zone.pid.ec`
- `zone.runtime_tuning_bundle`
- `zone.process_calibration.generic`
- `zone.process_calibration.solution_fill`
- `zone.process_calibration.tank_recirc`
- `zone.process_calibration.irrigation`
- `cycle.start_snapshot`
- `cycle.phase_overrides`
- `cycle.manual_overrides`

### 2.2 Что не входит в authority

Read-only operational facts читаются отдельно и не материализуются как config documents:

- `nodes`, `node_channels`, `channel_bindings`
- `pump_calibrations`
- `telemetry_last`, `telemetry_samples`
- `grow_cycles`, `grow_cycle_phases`, `zone_workflow_state`
- alerts, online/offline state, фактическая инфраструктура зоны

---

## 3. Компоненты системы

### 3.1 Registry

Schema-first реестр конфигов живёт в Laravel:

- `app/Services/AutomationConfigRegistry.php`

Registry определяет:

- namespace;
- `scope_type`;
- `schema_version`;
- `default_payload`;
- правила валидации;
- preset-capable namespaces.

### 3.2 Documents

Текущее authority-состояние хранится в таблице `automation_config_documents`.

Ключевые поля:

- `namespace`
- `scope_type`
- `scope_id`
- `schema_version`
- `payload`
- `status`
- `source`
- `checksum`
- `updated_by`

Для `zone.correction` outer document schema задаётся
`schemas/zone_correction_document.v1.json`:

- `payload.base_config` валидируется по `schemas/zone_correction.v1.json`;
- `payload.phase_overrides.{solution_fill|tank_recirc|irrigation}` ссылается на
  `schemas/zone_correction.v1.json#/$defs/PhaseOverride`;
- `PhaseOverride` — это **sparse diff** поверх `base_config`, а не полный snapshot
  `resolved_config`;
- compiler обязан сначала смержить `base_config + phase_overrides`, и только затем
  materialize-ить `resolved_config`.

Все изменения версии документа пишутся в `automation_config_versions`.

### 3.3 Bundles

Единственный runtime read-path:

- `automation_effective_bundles`

Bundle содержит:

- `scope_type`
- `scope_id`
- `bundle_revision`
- `schema_revision`
- `config`
- `violations`
- `status`
- `compiled_at`
- `inputs_checksum`

### 3.4 Violations

Compiler записывает machine-readable нарушения в:

- `automation_config_violations`

Violation shape:

- `namespace`
- `path`
- `code`
- `severity`
- `blocking`
- `message`

### 3.5 Presets

Preset subsystem используется для correction family и zone runtime tuning:

- `zone.correction`
- `zone.pid.ph`
- `zone.pid.ec`
- `zone.process_calibration.*`
- `zone.runtime_tuning_bundle`

Хранение:

- `automation_config_presets`
- `automation_config_preset_versions`

Правила:

- system presets read-only;
- custom presets editable;
- `Apply preset` копирует payload в draft/document;
- preset не является runtime authority и не создаёт live-link на документ.
- `zone.runtime_tuning_bundle` является application-layer preset document:
  он хранит `selected_preset_key`, `presets[]`, `advanced_overrides`, `resolved_preview`,
  но runtime напрямую его не читает.
- при `PUT zone.runtime_tuning_bundle` backend обязан atomically upsert-ить:
  - `zone.process_calibration.generic`
  - `zone.process_calibration.solution_fill`
  - `zone.process_calibration.tank_recirc`
  - `zone.process_calibration.irrigation`
  - `zone.pid.ph`
  - `zone.pid.ec`

---

## 4. Precedence и compilation

Единственный precedence:

`system.* -> zone.* -> cycle.*`

### 4.1 Compile rules

- любое изменение authority document триггерит пересборку затронутого scope;
- system update каскадно пересобирает zone и active grow-cycle bundles;
- zone update пересобирает zone bundle и active cycle bundles этой зоны;
- cycle update пересобирает bundle конкретного cycle;
- fallback на чтении не допускается;
- обязательные defaults материализуются как реальные documents.
- `zone.pid.ph`, `zone.pid.ec`, `zone.process_calibration.*` и `zone.runtime_tuning_bundle`
  materialize-ятся как bootstrap/system defaults и считаются launch-valid,
  если document schema-valid.

### 4.2 Runtime rules

- Laravel readiness/start path читает только compiled bundles и operational facts;
- AE3 использует только `bundle_revision`, привязанный к cycle snapshot;
- `grow_cycles.settings` хранит только immutable snapshot и `bundle_revision`, но не является authority.

---

## 5. Frontend contract

Web-admin не должен получать authority-конфиги через Inertia props.

Канонический frontend read/write path:

- `GET/PUT /api/automation-configs/{scopeType}/{scopeId}/{namespace}`
- `GET /api/automation-configs/{scopeType}/{scopeId}/{namespace}/history`
- `GET /api/automation-bundles/{scopeType}/{scopeId}` только для `system|zone|grow_cycle`
- `POST /api/automation-bundles/{scopeType}/{scopeId}/validate` только для `system|zone|grow_cycle`
- `GET /api/automation-presets/{namespace}`
- `POST /api/automation-presets/{namespace}`
- `PUT|PATCH /api/automation-presets/{presetId}`
- `DELETE /api/automation-presets/{presetId}`
- `POST /api/automation-presets/{presetId}/duplicate`

Frontend authority data layer должен строиться вокруг unified composable/store, а не вокруг page-props fallback.

Для `greenhouse.logic_profile` канонический read/write path идёт через raw authority document, а не через bundle endpoint.

---

## 6. Runtime usage

### 6.1 Laravel

Laravel использует authority для:

- system settings UI;
- zone correction/PID/process calibration editors;
- greenhouse/zone logic profile editors;
- readiness;
- grow cycle start.

Дополнительные ownership rules:

- low-level `two_tank_commands` в `zone.logic_profile` backend-owned:
  frontend больше не редактирует relay step-count и sequencing;
- если incoming `zone.logic_profile` не содержит `two_tank_commands`,
  backend сохраняет существующие custom commands зоны, а при их отсутствии
  materialize-ит defaults из `system.command_templates`;
- canonical owner `prepare_tolerance` для runtime correction:
  `zone.correction.resolved_config.phases.*.tolerance.prepare_tolerance`;
  legacy `zone.logic_profile.subsystems.diagnostics.execution.prepare_tolerance`
  допускается только как migration fallback;
- если irrigation decision strategy = `task`, timed irrigation (`mode`, `interval`, `duration`)
  является recipe-owned и zone override игнорируется compiler/runtime;
- если irrigation decision strategy = `smart_soil_v1`, trigger/config принадлежат zone automation;
- frontend больше не владеет `subsystems.irrigation.execution.correction_strategy`
  и `subsystems.irrigation.dosing_rules`: runtime derivation идёт из recipe/correction authority.

### 6.2 AE3 / Python

AE3 direct SQL read-model использует:

- `automation_effective_bundles`
- `grow_cycles.settings.bundle_revision`
- `zones.config_revision` — integer counter для live-mode hot-reload detection (Phase 5)

AE3 не должен собирать runtime-конфиг из таблиц вне authority или из `env()` business settings.

### 6.4 Config modes: locked vs live (Phase 5, 2026-04-15)

Zone имеет отдельный режим redactability, не путать с `control_mode` (who can issue commands):

- **`config_mode='locked'`** (default) — AE3 использует snapshot, зафиксированный при старте cycle. Правки конфига применяются только на next cycle.
- **`config_mode='live'`** (TTL-bounded) — AE3 `BaseStageHandler._checkpoint()` хот-свапит RuntimePlan при advance `zones.config_revision`. TTL auto-revert через `automation:revert-expired-live-modes` cron.

Revision-bump invariant:
- Любой PUT zone-scoped config (через `PUT /api/automation-configs/zone/{id}/{namespace}`) или live-edit recipe phase (через `PUT /api/grow-cycles/{id}/phase-config`) вызывает `ZoneConfigRevisionService::bumpAndAudit`:
  - Атомарный SQL `UPDATE zones SET config_revision = COALESCE(config_revision, 0) + 1 RETURNING` внутри `DB::transaction`
  - INSERT в `zone_config_changes` (unique `(zone_id, revision)` — correctness net)
- На AE3 стороне `_checkpoint` читает `config_revision`, сравнивает с `plan.runtime.config_revision`, при advance в live mode делает `PgZoneSnapshotReadModel().load()` + `resolve_two_tank_runtime_plan()` + `dataclasses.replace(plan, runtime=...)` → все downstream helpers видят fresh bundle

Cross-mode constraint:
- `control_mode='auto' + config_mode='live'` запрещён — блокируется в `ZoneConfigModeController::update` (409 `CONFIG_MODE_CONFLICT_WITH_AUTO`) и также в UI (disabled state)

Спецификация полная: см. `AE3_CONFIG_REFACTORING_PLAN.md` § Shipped feature summary и `ae3lite.md` § 6.6/7.5.

### 6.3 history-logger/common

Python common/runtime helpers могут читать system policy из authority documents, но не должны опираться на `system_automation_settings` как на источник истины.

---

## 7. Start-cycle contract

`POST /api/zones/{zone}/grow-cycles` работает только через authority cycle-documents:

1. сохранить `cycle.start_snapshot`
2. сохранить `cycle.phase_overrides`
3. сохранить `cycle.manual_overrides`
4. пересобрать bundle
5. проверить blocking violations
6. записать `grow_cycles.settings.bundle_revision`
7. только после этого запускать цикл

Post-create запись `phase_overrides` вне этого pipeline не допускается.

---

## 8. RBAC

- `admin` читает и меняет `system.*`, а также читает system bundles
- `operator|admin|agronomist|engineer` меняют `greenhouse.*`, `zone.*`, `cycle.*`, custom presets
- `viewer` читает только доступные `greenhouse|zone|grow_cycle` documents/bundles и readiness
- system presets read-only

Уточнение по `greenhouse.*`:
- `admin|agronomist` имеют доступ к greenhouse authority documents в setup/provisioning flow без explicit `user_greenhouses`
- `viewer|operator|engineer` требуют direct greenhouse ACL или доступ хотя бы к одной зоне внутри теплицы

Config modes (Phase 5):
- `setLive` policy (`ZonePolicy::setLive`) — включение `config_mode='live'` разрешено только `agronomist|engineer|admin`
- `operator` может переключать в `locked`, но не в `live` (возврат к snapshot допустим как safety action)
- `viewer` не меняет config mode
- live-edit `recipe.phase` (`PUT /api/grow-cycles/{id}/phase-config`) также требует `setLive` policy

---

## 8.1 Legacy mappings (system namespaces → SystemAutomationSettingsCatalog)

Пять system-namespaces имеют legacy-маппинг на `SystemAutomationSettingsCatalog`:

| Authority namespace | Legacy key | Callers |
|---------------------|------------|---------|
| `system.automation_defaults` | `automation_defaults` | `AutomationConfigRegistry::validate()`, `AutomationConfigController::serializeDocument()` |
| `system.command_templates` | `automation_command_templates` | то же |
| `system.process_calibration_defaults` | `process_calibration_defaults` | то же |
| `system.pump_calibration_policy` | `pump_calibration` | то же |
| `system.sensor_calibration_policy` | `sensor_calibration` | то же |

**Почему не удалено:** `SystemAutomationSettingsCatalog` остаётся единственным source of truth для:
- `defaults()` — дефолтные значения полей этих конфигов (в т.ч. `quality_score_legacy`);
- `fieldCatalog()` — метаданные полей для UI-редактора;
- `validate()` — валидация payload для этих namespaces.

`quality_score_legacy` — активное поле в `system.pump_calibration_policy`, используется в frontend TypeScript (`SystemSettings.ts`, `usePumpCalibrationSettings.ts`) и тестах. Это **не deprecated поле**, несмотря на слово "legacy" в имени — это legacy-score для backfill логики.

**Когда retirement:** retirement маппинга возможен после Phase 5 плана `AE_LEGACY_CLEANUP_PLAN.md` — когда генератор `tools/generate_zone_correction_catalog.py` будет расширен на system-namespaces и `SystemAutomationSettingsCatalog` будет полностью автогенерируемым. До тех пор маппинг — необходимый glue-layer.

**Методы:**
- `AutomationConfigRegistry::authorityToLegacySystemNamespace(string $namespace): ?string` — маппинг authority→legacy; `null` если не legacy-mapped.
- `AutomationConfigRegistry::legacySystemNamespaceToAuthority(string $namespace): ?string` — обратный маппинг.
- `AutomationConfigController::serializeLegacySystemDocument(string $legacyNamespace): array` — сериализует `defaults` + `field_catalog` из `SystemAutomationSettingsCatalog` для UI.

Эти методы **не удалять** без одновременного переноса `SystemAutomationSettingsCatalog` на autogeneration (Phase 5+).

---

## 9. Связанные документы

- `BACKEND_ARCH_FULL.md`
- `PYTHON_SERVICES_ARCH.md`
- `REST_API_REFERENCE.md`
- `../ARCHITECTURE_FLOWS.md`
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

### 9.1 Single source of truth: zone_correction default-значения

Файл **`schemas/zone_correction_defaults.json`** — единственный источник правды для default-значений конфига `zone_correction`.

| Слой | Файл / класс | Роль |
|------|--------------|------|
| JSON defaults | `schemas/zone_correction_defaults.json` | **Single source** — редактировать здесь |
| JSON Schema (constraints) | `schemas/zone_correction.v1.json` | Ограничения типов/диапазонов |
| PHP defaults | `ZoneCorrectionConfigCatalog::defaults()` | Должен совпадать с JSON-файлом — проверяется тестом |
| CI gate | `tools/generate_zone_correction_catalog.py --check` | Валидирует defaults против schema |
| Make target | `make check-config-catalog` | Запускает CI gate; включён в `make protocol-check` |
| PHP unit test | `tests/Unit/ZoneCorrectionCatalogDefaultsTest.php` | Проверяет совпадение PHP `defaults()` с JSON-файлом |

**Правило:** при изменении default-значения — обновить `zone_correction_defaults.json` **и** `ZoneCorrectionConfigCatalog::defaults()` одновременно. Тест не пройдёт при рассинхронизации.

<!-- BEGIN:generated-parameters -->

## Автогенерируемые таблицы параметров

> Секция генерируется `python3 tools/generate_authority.py` из `schemas/*.v1.json`.
> НЕ редактируй вручную — изменения будут перезаписаны.

### `system_automation_defaults`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |

### `zone_correction`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |
| `controllers` | object | — | ✓ |
| `controllers.ec` | — | — | ✓ |
| `controllers.ph` | — | — | ✓ |
| `dosing` | object | — | ✓ |
| `dosing.dose_ec_channel` | string | minLength=1, maxLength=64 | ✓ |
| `dosing.dose_ph_down_channel` | string | minLength=1, maxLength=64 | ✓ |
| `dosing.dose_ph_up_channel` | string | minLength=1, maxLength=64 | ✓ |
| `dosing.ec_dosing_mode` | enum: `single` \| `multi_parallel` \| `multi_sequential` | — | ✓ |
| `dosing.max_ec_dose_ml` | number | minimum=0.1, maximum=1000.0 | ✓ |
| `dosing.max_ph_dose_ml` | number | minimum=0.1, maximum=1000.0 | ✓ |
| `dosing.solution_volume_l` | number | minimum=1.0, maximum=10000.0 | ✓ |
| `ec_component_policy` | object | — |  |
| `ec_component_ratios` | object | — |  |
| `ec_dosing_mode` | enum: `single` \| `multi_parallel` \| `multi_sequential` | — |  |
| `ec_excluded_components` | array | — |  |
| `retry` | object | — | ✓ |
| `retry.decision_window_retry_sec` | integer | minimum=1, maximum=3600 | ✓ |
| `retry.low_water_retry_sec` | integer | minimum=1, maximum=3600 | ✓ |
| `retry.max_ec_correction_attempts` | integer | minimum=1, maximum=500 | ✓ |
| `retry.max_ph_correction_attempts` | integer | minimum=1, maximum=500 | ✓ |
| `retry.prepare_recirculation_correction_slack_sec` | integer | minimum=0, maximum=7200 | ✓ |
| `retry.prepare_recirculation_max_attempts` | integer | minimum=1, maximum=10 | ✓ |
| `retry.prepare_recirculation_max_correction_attempts` | integer | minimum=1, maximum=500 | ✓ |
| `retry.prepare_recirculation_timeout_sec` | integer | minimum=30, maximum=7200 | ✓ |
| `retry.telemetry_stale_retry_sec` | integer | minimum=1, maximum=3600 | ✓ |
| `runtime` | object | — | ✓ |
| `runtime.clean_fill_retry_cycles` | integer | minimum=0, maximum=20 | ✓ |
| `runtime.clean_fill_timeout_sec` | integer | minimum=30, maximum=86400 | ✓ |
| `runtime.clean_max_sensor_label` | string | minLength=1, maxLength=128 | ✓ |
| `runtime.clean_min_sensor_label` | string | minLength=1, maxLength=128 | ✓ |
| `runtime.level_switch_on_threshold` | number | minimum=0.0, maximum=1.0 | ✓ |
| `runtime.required_node_type` | string | minLength=1, maxLength=64 | ✓ |
| `runtime.solution_fill_timeout_sec` | integer | minimum=30, maximum=86400 | ✓ |
| `runtime.solution_max_sensor_label` | string | minLength=1, maxLength=128 | ✓ |
| `runtime.solution_min_sensor_label` | string | minLength=1, maxLength=128 | ✓ |
| `safety` | object | — | ✓ |
| `safety.block_on_active_no_effect_alert` | boolean | — | ✓ |
| `safety.safe_mode_on_no_effect` | boolean | — | ✓ |
| `system_type` | string | minLength=1, maxLength=64 |  |
| `timing` | object | — | ✓ |
| `timing.irr_state_max_age_sec` | integer | minimum=5, maximum=3600 | ✓ |
| `timing.level_poll_interval_sec` | integer | minimum=5, maximum=3600 | ✓ |
| `timing.sensor_mode_stabilization_time_sec` | integer | minimum=0, maximum=3600 | ✓ |
| `timing.stabilization_sec` | integer | minimum=0, maximum=3600 | ✓ |
| `timing.telemetry_max_age_sec` | integer | minimum=5, maximum=3600 | ✓ |
| `tolerance` | object | — | ✓ |
| `tolerance.prepare_tolerance` | object | — | ✓ |
| `tolerance.prepare_tolerance.ec_pct` | number | minimum=0.1, maximum=100.0 | ✓ |
| `tolerance.prepare_tolerance.ph_pct` | number | minimum=0.1, maximum=100.0 | ✓ |

### `zone_correction_document`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |
| `base_config` | — | — | ✓ |
| `last_applied_at` | string \| null | — |  |
| `last_applied_version` | integer \| null | — |  |
| `phase_overrides` | oneOf | — | ✓ |
| `preset_id` | string \| null | minLength=1, maxLength=128 | ✓ |
| `resolved_config` | object | — | ✓ |

### `zone_logic_profile`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |
| `active_mode` | string \| null | minLength=1, maxLength=64 | ✓ |
| `profiles` | object | — | ✓ |

### `zone_pid`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |
| `close_zone` | number | maximum=20.0, exclusiveMinimum=0.0 | ✓ |
| `dead_zone` | number | maximum=10.0, exclusiveMinimum=0.0 | ✓ |
| `far_zone` | number | maximum=50.0, exclusiveMinimum=0.0 | ✓ |
| `max_integral` | number | maximum=500.0, exclusiveMinimum=0.0 | ✓ |
| `zone_coeffs` | object | — | ✓ |
| `zone_coeffs.close` | — | — | ✓ |
| `zone_coeffs.far` | — | — | ✓ |

### `zone_process_calibration`

| Path | Type | Constraints | Required |
| --- | --- | --- | --- |
| `confidence` | number | minimum=0.0, maximum=1.0 | ✓ |
| `ec_gain_per_ml` | number | minimum=0.0, maximum=10.0 | ✓ |
| `ec_per_ph_ml` | number | minimum=-1.0, maximum=1.0 | ✓ |
| `is_active` | boolean | — |  |
| `meta` | oneOf | — |  |
| `mode` | enum: `generic` \| `solution_fill` \| `tank_recirc` \| `irrigation` | — | ✓ |
| `ph_down_gain_per_ml` | number | minimum=0.0, maximum=10.0 | ✓ |
| `ph_per_ec_ml` | number | minimum=-1.0, maximum=1.0 | ✓ |
| `ph_up_gain_per_ml` | number | minimum=0.0, maximum=10.0 | ✓ |
| `settle_sec` | integer | minimum=0, maximum=600 | ✓ |
| `source` | string | minLength=1, maxLength=64 | ✓ |
| `transport_delay_sec` | integer | minimum=0, maximum=600 | ✓ |
| `updated_at` | string \| null | — |  |
| `valid_from` | string \| null | — |  |
| `valid_to` | string \| null | — |  |

<!-- END:generated-parameters -->
