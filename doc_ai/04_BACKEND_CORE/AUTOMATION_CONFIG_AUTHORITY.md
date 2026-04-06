# AUTOMATION_CONFIG_AUTHORITY.md
# Единый authority automation/runtime-конфигов

**Версия:** 1.0  
**Дата обновления:** 2026-04-06  
**Статус:** Канонично для Laravel runtime, AE3 read-model и web-admin

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

AE3 не должен собирать runtime-конфиг из таблиц вне authority или из `env()` business settings.

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

---

## 9. Связанные документы

- `BACKEND_ARCH_FULL.md`
- `PYTHON_SERVICES_ARCH.md`
- `REST_API_REFERENCE.md`
- `../ARCHITECTURE_FLOWS.md`
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
