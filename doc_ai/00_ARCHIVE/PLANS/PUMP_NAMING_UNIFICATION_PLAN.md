# PUMP_NAMING_UNIFICATION_PLAN.md
# План унификации имён насосов по всей системе

**Версия:** 1.0  
**Дата обновления:** 2026-04-13  
**Статус:** Draft / Approved for implementation planning

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: после завершения плана runtime, API, authority-configs и UI больше не принимают legacy alias имён насосов.

---

## 1. Цель

Убрать из системы множественные идентификаторы одного и того же насоса и перейти к одному каноническому имени на всех слоях:

- firmware / NodeConfig;
- MQTT и history-logger;
- Laravel DB / readiness / setup wizard / automation authority;
- automation-engine (AE3);
- frontend DTO / UI / alerts / tests.

Итоговый инвариант:

> один физический насос = одно каноническое имя = один channel id во всей системе.

Semantic metadata (`component=npk`, `component=ph_down` и т.п.) остаётся отдельным полем и не кодируется в имени насоса.

---

## 2. Текущая проблема

Сейчас один и тот же насос может фигурировать под разными именами:

- физический channel:
  - `pump_acid`, `pump_base`, `pump_a`, `pump_b`, `pump_c`, `pump_d`, `pump_main`;
- semantic binding role:
  - `ph_acid_pump`, `ph_base_pump`, `ec_npk_pump`, `ec_calcium_pump`, `ec_magnesium_pump`, `ec_micro_pump`, `main_pump`;
- correction/runtime aliases:
  - `dose_ph_down`, `dose_ph_up`, `dose_ec_a`, `dose_ec_b`, `dose_ec_c`, `dose_ec_d`;
- firmware/test-node backward-compat aliases:
  - `ph_doser_down`, `ph_doser_up`, `pump_irrigation`.

Из-за этого:

- config documents и compiled bundles содержат не физические имена, а semantic aliases;
- `channel_bindings.role` и `node_channels.channel` живут в разных словарях;
- AE3 вынужден резолвить alias-слой вместо прямой работы с `channel`;
- frontend и alert payloads иногда показывают `channel`, иногда `binding_role`;
- появляются ложные конфликты, как в `multi_parallel`, когда один насос попадает в runtime map под несколькими alias.

---

## 3. Целевой контракт

### 3.1. Каноническое правило

Для насосов канонический идентификатор системы равен имени физического канала из `NodeConfig` / `node_channels.channel`.

Для correction и irrigation v1 фиксируем следующий canonical set:

| Назначение | Каноническое имя |
|---|---|
| pH acid pump | `pump_acid` |
| pH base pump | `pump_base` |
| EC NPK pump | `pump_a` |
| EC Calcium pump | `pump_b` |
| EC Magnesium pump | `pump_c` |
| EC Micro pump | `pump_d` |
| Main irrigation pump | `pump_main` |
| Fill/input pump, если есть как отдельный физический канал | `pump_in` |

### 3.2. Что запрещается после миграции

Следующие строки перестают быть допустимыми runtime identifiers:

- `ph_acid_pump`, `ph_base_pump`;
- `ec_npk_pump`, `ec_calcium_pump`, `ec_magnesium_pump`, `ec_micro_pump`;
- `dose_ph_down`, `dose_ph_up`;
- `dose_ec_a`, `dose_ec_b`, `dose_ec_c`, `dose_ec_d`;
- `main_pump`;
- `pump_irrigation`;
- `ph_doser_down`, `ph_doser_up`.

Они допускаются только:

- в one-shot миграции данных;
- в repair scripts для уже существующих dev/staging записей;
- в исторических логах как legacy payload.

В live runtime, API request payloads, authority docs и UI forms эти значения больше не принимаются.

### 3.3. Роли и компоненты

Чтобы убрать dual vocabulary, для насосов `channel_bindings.role` тоже должен совпадать с canonical channel name:

- `ph_acid_pump` -> `pump_acid`
- `ph_base_pump` -> `pump_base`
- `ec_npk_pump` -> `pump_a`
- `ec_calcium_pump` -> `pump_b`
- `ec_magnesium_pump` -> `pump_c`
- `ec_micro_pump` -> `pump_d`
- `main_pump` -> `pump_main`

При этом смысл насоса хранится отдельно:

- `pump_calibrations.component`: `ph_down | ph_up | npk | calcium | magnesium | micro`;
- UI label: `Насос pH кислоты`, `Насос EC NPK` и т.д.;
- node type / zone topology / business rules.

Идентификатор и семантика больше не смешиваются.

---

## 4. Область изменений

### 4.1. Firmware / hardware docs

Нужно привести к одному контракту:

- `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
- `02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
- `02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`
- `02_HARDWARE_FIRMWARE/TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md`
- `02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`

### 4.2. MQTT / backend contracts

Нужно убрать semantic pump aliases из:

- `03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md`
- `04_BACKEND_CORE/HISTORY_LOGGER_API.md`

### 4.3. Data / DB

Нужно обновить:

- `channel_bindings.role`
- zone readiness required bindings
- setup wizard binding specs
- `zone.correction.*.dose_*_channel`
- grow-cycle snapshots / compiled bundles
- tests/seeders/migrations, где зашиты legacy pump ids.

### 4.4. AE3 runtime

Нужно убрать alias resolution из:

- `cycle_start_planner.py`
- correction planner / runtime actuator maps
- zone snapshot read-model normalization
- runtime alert / event payloads.

### 4.5. Frontend

Нужно убрать поддержку legacy pump ids из:

- setup wizard device matching;
- readiness cards;
- calibration panels;
- zone automation editors;
- alert / event formatters;
- test fixtures.

---

## 5. План реализации

### Фаза 0. Freeze и инвентаризация

Цель:

- зафиксировать canonical vocabulary;
- выписать все legacy identifiers и места их использования;
- запретить добавление новых alias в код.

Задачи:

- создать единый mapping table `legacy -> canonical`;
- отметить в документации, какие alias являются firmware-only historical compatibility;
- собрать список DB payloads, которые нужно переписать миграцией.

Результат:

- один утверждённый mapping document;
- список затронутых файлов/таблиц для implementation phase.

### Фаза 1. Спецификации и контракты

Цель:

- сначала переписать Markdown-истину, потом код.

Задачи:

- во всех спецификациях correction и setup заменить `ec_npk_pump`/`ph_acid_pump` на `pump_a`/`pump_acid`;
- в API и examples перестать публиковать `binding_role=ph_acid_pump` и т.п.;
- зафиксировать, что для насосов canonical identifier = `channel`.

Результат:

- `doc_ai/` не содержит conflicting canonical names для одних и тех же насосов.

### Фаза 2. Laravel / DB canonicalization

Цель:

- перевести persisted данные и конфиги на единые имена.

Задачи:

- добавить Laravel migration для rewrite:
  - `channel_bindings.role`
  - zone/grow-cycle automation docs (`zone.correction`, snapshots, если persisted)
  - seed data и default payloads;
- обновить `PumpCalibrationCatalog`, `ZoneReadinessService`, `SetupWizardController`,
  `ZonePumpCalibrationsController`, `SimulationOrchestratorService`;
- перестать использовать role names `ph_acid_pump|ec_npk_pump|main_pump` как primary ids.

Правило:

- миграция данных может читать legacy значения;
- runtime код после релиза должен писать только canonical names.

### Фаза 3. AE3 runtime cleanup

Цель:

- убрать alias-resolver из planning path.

Задачи:

- удалить fallback-логики вида `ec_npk_pump -> pump_a`, `dose_ec_a -> pump_a`, `ph_acid_pump -> pump_acid`;
- сделать так, чтобы `snapshot.actuators`, correction config и dose plans оперировали только canonical channel names;
- сохранить fail-closed поведение на unknown channel вместо silent alias fallback.

Результат:

- AE3 не имеет internal alias dictionary для pump naming;
- planner не строит `ec_actuators` map с несколькими ключами для одного насоса.

### Фаза 4. Frontend / UX cleanup

Цель:

- показывать пользователю один и тот же id во всех местах.

Задачи:

- setup wizard подбирает и сохраняет только canonical names;
- readiness/checklist/calibration UI читает `binding_role == channel` для насосов;
- human-readable labels остаются отдельными (`Насос EC NPK`), но технический id один;
- удалить из composables массивы alias-кандидатов (`pump_a|ec_npk_pump|dose_ec_a` и т.д.).

Результат:

- ни один UI flow не ожидает legacy pump alias.

### Фаза 5. Firmware / test-node cleanup

Цель:

- завершить переход на канонические channel ids на краю системы.

Задачи:

- для real nodes оставить только канонические pump channel names в `config_report`;
- test-node и compatibility shims перевести в режим strict canonical naming;
- historical alias-команды оставить только если это необходимо для локальной отладки firmware, но не отражать их в backend contract.

Результат:

- `config_report` и device protocol больше не рекламируют semantic pump aliases как valid external ids.

### Фаза 6. Cleanup и observability

Цель:

- убедиться, что alias-слой реально умер.

Задачи:

- добавить grep/check в CI на запрещённые идентификаторы;
- проверить alert payloads, zone_events, readiness responses, automation-state payloads;
- удалить временные migration helpers и compatibility branches.

Результат:

- в runtime code и спецификациях не остаётся legacy pump ids.

---

## 6. Правила миграции данных

### 6.1. Rewrite table

| Legacy | Canonical |
|---|---|
| `ph_acid_pump` | `pump_acid` |
| `ph_base_pump` | `pump_base` |
| `ec_npk_pump` | `pump_a` |
| `ec_calcium_pump` | `pump_b` |
| `ec_magnesium_pump` | `pump_c` |
| `ec_micro_pump` | `pump_d` |
| `dose_ph_down` | `pump_acid` |
| `dose_ph_up` | `pump_base` |
| `dose_ec_a` | `pump_a` |
| `dose_ec_b` | `pump_b` |
| `dose_ec_c` | `pump_c` |
| `dose_ec_d` | `pump_d` |
| `main_pump` | `pump_main` |
| `pump_irrigation` | `pump_main` |
| `ph_doser_down` | `pump_acid` |
| `ph_doser_up` | `pump_base` |

### 6.2. Migration policy

- rewriting должен быть one-way;
- старые значения не должны сохраняться после повторного compile/save;
- runtime fallback по legacy ids после миграции запрещён;
- если в БД найдены unknown aliases вне mapping table, migration должна падать fail-closed.

---

## 7. Критерии готовности

- `channel_bindings.role` для насосов совпадает с `node_channels.channel`.
- `zone.correction.*.dose_*_channel` хранит только `pump_*`.
- AE3 planners и read-model не содержат alias map для pump naming.
- Laravel readiness/setup/calibration flows не используют `ph_acid_pump|ec_npk_pump|main_pump` как primary ids.
- Frontend tests и fixtures больше не подают legacy pump aliases.
- Документация `doc_ai/` не содержит conflicting canonical names для одних и тех же насосов.
- CI/grep-check подтверждает отсутствие запрещённых legacy pump ids в runtime code.

---

## 8. Риски и открытые вопросы

### 8.1. `main_pump` / `pump_main`

Сейчас irrigation path уже largely canonicalized в пользу `pump_main`, но readiness/setup/UI ещё используют `main_pump`.
Нужно подтвердить, что для всех топологий canonical id именно `pump_main`, а не topology-specific role.

### 8.2. `pump_in`

`pump_in` местами используется как physical channel, а местами как service/process label.
Перед strict cleanup нужно разделить:

- physical actuator channel `pump_in`;
- business-process flag `active_processes.pump_in`.

Они не должны смешиваться.

### 8.3. Непомповые water aliases

Этот план покрывает именно насосы.
Alias-слой для `drain`, `fill_valve`, `drain_main`, `water_control` и других water/valve identifiers требует отдельной canonicalization task.

---

## 9. Рекомендуемый порядок implementation tasks

1. Обновить системные и контрактные Markdown-спецификации.
2. Подготовить Laravel migration на rewrite persisted names.
3. Перевести Laravel services / seeders / API DTO.
4. Удалить alias-резолверы из AE3 runtime.
5. Перевести frontend composables/tests.
6. Очистить firmware/test-node compatibility docs и adapters.
7. Добавить CI-check на запрещённые identifiers.

