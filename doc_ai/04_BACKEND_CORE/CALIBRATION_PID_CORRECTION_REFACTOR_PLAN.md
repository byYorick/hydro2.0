# План выравнивания calibration / PID / correction

**Версия:** 1.0  
**Дата:** 2026-03-17  
**Статус:** Рабочий план, приведённый к текущим контрактам репозитория

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Зафиксировать безопасный план улучшений для pump calibration, process calibration,
PID-конфигов и correction UI без поломки защищённого пайплайна:

`Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`

План сознательно не вводит новый runtime path, новый MQTT-контракт или новый source of truth
для уже существующих calibration/PID данных.

## Контекст

Проблема текущего состояния не в отсутствии базовых сущностей, а в разрыве между:

- реальными runtime/data contracts;
- Laravel/API/UI представлением;
- UX-слоем вокруг коррекции и калибровок.

Отдельно важно: в репозитории уже существуют `pump_calibrations`,
`zone_process_calibrations`, `pid_state`, `zone_pid_configs`, а также zone-level override
для `pump_calibration` внутри `zone_correction_configs`.

## Неподвижные инварианты

1. Device-команды публикуются только через `history-logger POST /commands`.
2. Прямой MQTT publish из Laravel/scheduler/automation-engine запрещён.
3. Runtime path correction остаётся на direct SQL read-model.
4. Новый correction runtime или параллельный PID runtime этим планом не создаётся.
5. Изменения БД допускаются только через Laravel migrations.
6. Если меняются data/API-контракты, синхронно обновляются `doc_ai/*` source-of-truth.

## Текущий canonical baseline

### 1. Pump calibration

- Ручные калибровки дозирующих каналов хранятся в `pump_calibrations`.
- Runtime bounds/defaults для pump calibration берутся из
  `system_automation_settings(namespace='pump_calibration')`.
- Zone-level override для runtime pump calibration хранится в
  `zone_correction_configs.base_config.pump_calibration`.
- Полный runtime payload раскрывается в
  `zone_correction_configs.resolved_config.pump_calibration`.
- `node_channels.config.pump_calibration` допустим только как mirror/manual payload.

Следствие:
- новая таблица наподобие `zone_pump_calibration_settings` в этом плане не вводится;
- разделение UX и read/write API строится поверх существующих контрактов.

### 2. Process calibration

- Process-level calibration уже хранится в `zone_process_calibrations`.
- Canonical storage keys для `zone_process_calibrations.mode` ограничены
  `generic|solution_fill|tank_recirc|irrigation`.
- Runtime workflow aliases нормализуются к этим ключам:
  `tank_filling -> solution_fill`,
  `prepare_recirculation -> tank_recirc`,
  `irrigating|irrig_recirc -> irrigation`.
- `transport_delay_sec` и `settle_sec` для in-flow correction берутся именно оттуда.
- При отсутствии process calibration новый in-flow correction path должен идти fail-closed.

Следствие:
- UI и validation должны усиливать этот контракт, а не заменять его.

### 3. PID

В репозитории есть два слоя, которые сейчас нельзя смешивать без явного решения:

- Laravel/API слой `zone_pid_configs`;
- runtime semantics, которые в текущих domain docs описаны через `zone_correction_configs`.

Следствие:
- этот план не меняет canonical owner PID для runtime без отдельного архитектурного решения;
- улучшения PID в текущей итерации ограничиваются event/log UX, history UX и валидацией
  существующего Laravel path;
- миграция ownership PID между `zone_pid_configs` и `zone_correction_configs`
  вынесена в отдельный decision track.

## Область работ этой итерации

### Входит

1. Выравнивание документации и формулировок под фактические контракты.
2. Безопасные Laravel-фиксы:
   - `ZoneEvent` payload consistency;
   - runtime-safe validation для `zone_process_calibrations`;
   - тесты для новых/уточнённых правил.
3. UI-улучшения, не меняющие ownership данных:
   - process calibration panel поверх существующих endpoint-ов;
   - улучшение explanatory UX для correction settings;
   - улучшение pump calibration panel поверх `pump_calibrations` и `correction-config`.

### Не входит

1. Новый storage source of truth для pump calibration.
2. Новый MQTT/history-logger контракт.
3. Новый ingress для correction runtime.
4. Перенос runtime PID owner между `zone_pid_configs` и `zone_correction_configs`.
5. Вторая реализация correction runtime рядом с текущей sub-machine.

## Фазы реализации

### Фаза 1. Contract hardening

**Цель:** убрать несогласованность в существующих Laravel/data contracts без изменения архитектуры.

#### 1.1 `ZoneEvent` consistency

Привести события PID/process calibration к каноническому `payload_json`.

Сюда входит:

- `ZonePidConfigService` пишет `payload_json`, а не только `details`;
- тесты PID log/history используют актуальный payload path;
- read-layer через `details` сохраняется только как backward-compatible accessor.

#### 1.2 Process calibration validation hardening

Сузить validation диапазоны к runtime-safe границам для ручного UI:

```text
ec_gain_per_ml:       0.001 .. 10
ph_up_gain_per_ml:    0.001 .. 5
ph_down_gain_per_ml:  0.001 .. 5
ph_per_ec_ml:        -2 .. 2
ec_per_ph_ml:        -2 .. 2
transport_delay_sec:  0 .. 120
settle_sec:           0 .. 300
confidence:           0 .. 1
```

Нулевая gain-калибровка для ручного production path не допускается.

#### 1.3 Документирование тестового контракта

Обязательные тесты:

- feature: upsert process calibration with valid narrow bounds;
- feature: reject out-of-range process calibration;
- feature/unit: PID config update writes canonical event payload.

### Фаза 2. Process calibration UX

**Цель:** сделать `zone_process_calibrations` понятным UI-слоем без изменения storage contract.

#### 2.1 Единая панель process calibration

Новый UI работает поверх существующих endpoint-ов:

- `GET /api/zones/{zone}/process-calibrations`
- `GET /api/zones/{zone}/process-calibrations/{mode}`
- `PUT /api/zones/{zone}/process-calibrations/{mode}`

Панель должна:

- показывать `solution_fill`, `tank_recirc`, `irrigation`, `generic`;
- явно объяснять связь `transport_delay_sec + settle_sec = observe window`;
- отображать `confidence`, `source`, `valid_from`;
- не скрывать, что runtime fallback идёт в `generic`, а при его отсутствии работает fail-closed.

#### 2.2 Recommended values

Допустимо добавить read-only рекомендации рядом с полями, если:

- расчёт строится только по существующим `zone_events`/telemetry данным;
- recommendation не становится новым source of truth;
- сохранение по-прежнему идёт только через явный `PUT`.

### Фаза 3. Pump calibration UX без смены ownership

**Цель:** улучшить калибровку насосов, сохранив текущую модель хранения.

#### 3.1 Что остаётся как есть

- активная ручная калибровка сохраняется в `pump_calibrations`;
- системные min/max/defaults живут в `system_automation_settings(namespace='pump_calibration')`;
- zone override для runtime bounds живёт в `correction-config.base_config.pump_calibration`.

#### 3.2 Что можно улучшать

- `PumpCalibrationsPanel.vue`:
  - `quality_score`;
  - возраст калибровки;
  - явный `component`;
  - быстрый переход к перекалибровке.
- `ZonePumpCalibrationSettingsCard.vue`:
  - редактирует только zone override в `correction-config`;
  - не создаёт новый backend storage.

#### 3.3 Запуск насоса из UI

Отдельный Laravel endpoint допускается только как thin wrapper над уже существующим
command path и только при соблюдении условий:

1. команда уходит через существующий Laravel -> PythonBridge/history-logger path;
2. response/status model не придумывается заново, а явно маппится на canonical `commands.status`;
3. контракт и mapping документируются в `API_SPEC_FRONTEND_BACKEND_FULL.md` и
   `HISTORY_LOGGER_API.md`, если реально меняется surface area.

До фиксации этого mapping запуск насоса считается отдельным подпунктом, а не стартовой задачей.

### Фаза 4. Correction UX simplification

**Цель:** упростить интерфейс correction config без изменения runtime contract.

Допустимые улучшения:

- explanatory copy для `no_effect_consecutive_limit`;
- preview effective config;
- упрощённый quick-mode поверх уже существующего `correction-config`,
  если он не скрывает phase-specific effect от пользователя окончательно;
- rollback existing correction config versions, если он реализуется как создание новой версии
  из старой, а не мутирование исторической записи.

Недопустимо в этой фазе:

- убирать phase overrides из data model;
- вводить новый runtime endpoint для effective config;
- переносить PID owner в рамках этой же задачи.

### Фаза 5. PID improvements без смены runtime owner

**Цель:** улучшить Laravel-side эксплуатацию PID, не принимая скрытого архитектурного решения.

Разрешено:

- улучшить `PID_CONFIG_UPDATED` events/log UX;
- улучшить PID history/log display;
- добавить rollback/history для `zone_pid_configs`, если это остаётся чисто Laravel-side contract.

Запрещено без отдельного design decision:

- объявлять `zone_pid_configs` новым runtime owner;
- одновременно хранить и редактировать PID как canonical truth в двух разных местах.

## Первый implementation slice

Стартуем с Фазы 1:

1. поправить `ZoneEvent` payload consistency для PID;
2. ужесточить validation для `UpsertZoneProcessCalibrationRequest`;
3. обновить/добавить feature tests;
4. только после этого переходить к UI-слою.

Причина выбора:

- это не ломает protected pipeline;
- не конфликтует с текущим `pump_calibration` ownership;
- даёт immediate value и уменьшает двусмысленность контрактов;
- не требует входа в спорный runtime ownership PID.

## Затронутые файлы первой итерации

```text
backend/laravel/app/Services/ZonePidConfigService.php
backend/laravel/app/Http/Requests/UpsertZoneProcessCalibrationRequest.php
backend/laravel/tests/Feature/ZoneProcessCalibrationControllerTest.php
backend/laravel/tests/Feature/ZonePidConfigControllerTest.php
backend/laravel/tests/Unit/Services/ZonePidConfigServiceTest.php
```

Runtime-файлы `automation-engine/ae3lite/*` в первый slice не входят, пока не проверено,
что локальные незакоммиченные изменения в них не конфликтуют с новой работой.

## Критерии приёмки первой итерации

- `PID_CONFIG_UPDATED` пишет канонический payload в `zone_events.payload_json`.
- Process calibration API отклоняет unsafe ручные значения вне согласованных диапазонов.
- Feature/unit tests покрывают оба изменения.
- Документ и код не вводят новый source of truth для `pump_calibration`.
- Документ и код не вводят новый command status contract мимо `history-logger`.

## Открытые вопросы, вынесенные за рамки этой итерации

1. Какой слой является canonical runtime owner PID: `zone_pid_configs` или `zone_correction_configs`.
2. Нужен ли отдельный thin endpoint для pump calibration run, или достаточно reuse existing command API.
3. Нужна ли отдельная версия history/restore для PID, или достаточно audit trail + event log.
