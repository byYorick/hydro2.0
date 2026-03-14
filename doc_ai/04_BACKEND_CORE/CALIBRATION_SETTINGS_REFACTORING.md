# Рефакторинг: Калибровка насосов и сенсоров — настройки в БД + управление калибровкой сенсоров

**Статус:** TODO
**Ветка:** ae3
**Дата создания:** 2026-03-13

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Связанные документы

- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`
- `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`

---

## Проблема

Две связанные проблемы:

1. **Пороги калибровки насосов захардкожены** — ~15 констант в 4 файлах.
   Диапазон `ml_per_sec` рассогласован: Laravel `[0.01, 20]`, AE `[0.01, 100]`,
   history-logger — без проверки. Оператор не может изменить ни одно значение
   без редактирования кода.

2. **Калибровка сенсоров pH/EC не управляется с backend** — сейчас только
   MQTT-команда `calibrate(stage, known_ph/tds_value)` напрямую на узел.
   Нет: API, UI, истории калибровок, напоминаний о просроченных калибровках,
   отслеживания статуса.

## Scope (что входит)

| Подсистема | Что делаем |
|-----------|-----------|
| **Pump calibration settings** | Перенос ~15 захардкоженных констант в БД + UI настроек |
| **Sensor calibration system** | Новая фича: таблица, API, MQTT интеграция, UI wizard, история, напоминания |

**НЕ входит** (отдельные задачи):
- Water & pump safety thresholds
- Anomaly detection thresholds
- Command timing / PID thresholds
- Digital Twin model calibration thresholds
- Relay Autotune (будет отдельная умная система)

---

## Часть A: Настройки калибровки насосов → БД

### Архитектурные инварианты

- `system_automation_settings` — единственный источник дефолтов для `pump_calibration` и `sensor_calibration`.
- `zone_correction_configs.resolved_config.pump_calibration` — только zone-level override; путь фиксируется именно как `resolved_config.pump_calibration`, без промежуточного `base`.
- `ZoneCorrectionConfigCatalog` не получает runtime defaults для `pump_calibration`, чтобы не дублировать source of truth.
- Для команд сенсорной калибровки сохраняется канонический command flow:
  `Laravel -> history-logger POST /commands -> MQTT -> ESP32`.
- Новый специализированный publish endpoint в history-logger не вводится, если можно использовать существующий `POST /commands`.

### Архитектура

```
Zone request → zone_correction_configs.resolved_config.pump_calibration (zone-level override)
                        ↓ если секция не задана
               system_automation_settings namespace='pump_calibration' (system-level)
```

**НЕТ hardcoded fallback.** Миграция seed'ит дефолты.
Код читает только из БД. Если записи нет — `RuntimeError` (fail-loud).

### Потребители

| Сервис | Как читает |
|--------|-----------|
| AE (correction_planner.py) | `ZoneSnapshot.correction_config.pump_calibration` (уже загружается из `zone_correction_configs`) |
| History-logger (water_flow.py) | SQL запрос `system_automation_settings` |
| Laravel (controllers) | `SystemAutomationSetting::forNamespace('pump_calibration')` → cache 300с |
| Frontend (Vue) | Inertia props `pumpCalibrationSettings` + system settings API |

### Namespace: `pump_calibration`

| Ключ | Default | Описание | Тип | Min | Max |
|------|---------|----------|-----|-----|-----|
| `ml_per_sec_min` | 0.01 | Минимальная скорость насоса (мл/с) | number | 0.001 | 1.0 |
| `ml_per_sec_max` | 20.0 | Максимальная скорость насоса (мл/с) | number | 5.0 | 200.0 |
| `min_dose_ms` | 50 | Минимальная длительность импульса (мс) | integer | 10 | 500 |
| `calibration_duration_min_sec` | 1 | Мин. время прогона при калибровке (сек) | integer | 1 | 10 |
| `calibration_duration_max_sec` | 120 | Макс. время прогона при калибровке (сек) | integer | 30 | 600 |
| `quality_score_basic` | 0.75 | Оценка качества без K-коэффициента | number | 0.0 | 1.0 |
| `quality_score_with_k` | 0.90 | Оценка качества с K-коэффициентом | number | 0.0 | 1.0 |
| `quality_score_legacy` | 0.50 | Оценка качества для legacy backfill | number | 0.0 | 1.0 |
| `age_warning_days` | 30 | Предупреждение о возрасте калибровки (дни) | integer | 1 | 365 |
| `age_critical_days` | 90 | Критичный возраст калибровки (дни) | integer | 7 | 365 |
| `default_run_duration_sec` | 20 | Длительность по умолчанию в UI (сек) | integer | 5 | 60 |

### Захардкоженные источники (удалить после переноса)

| Источник | Переменная/значение | Файл:строка |
|----------|-------------------|-------------|
| `_MIN_DOSE_MS = 50` | min_dose_ms | `correction_planner.py:37` |
| `0.01` / `100.0` | ml_per_sec_min/max | `correction_planner.py:582` |
| `min:0.01, max:20` | ml_per_sec_min/max | `ZonePumpCalibrationsController.php:126` |
| `min="0.01" max="20"` | ml_per_sec_min/max | `PumpCalibrationsPanel.vue:62-63` |
| `quality_score = 0.9 if ... else 0.75` | quality_score_* | `water_flow.py:1096` |
| `> 30` (дней) | age_warning_days | `PumpCalibrationsPanel.vue:79` |
| `duration_sec = ref(20)` | default_run_duration_sec | `usePumpCalibration.ts:45` |
| `min: 1, max: 120` | calibration_duration_* | `usePumpCalibration.ts:314` |
| `min="1" max="120"` | calibration_duration_* | `PumpCalibrationModal.vue:64-65` |
| `ge=1, le=120` | calibration_duration_* | `history-logger/models.py:117` |

---

## Часть B: Система калибровки сенсоров pH/EC

### Текущее состояние

Сейчас калибровка pH/EC сенсоров — **только firmware-level**:

```
Пользователь → MQTT напрямую на узел → ESP32 → I2C → Trema sensor EEPROM
```

- pH: `calibrate(stage=1|2, known_ph=0.0-14.0)` → `trema_ph_calibrate()`
- EC: `calibrate(stage=1|2, tds_value=0-10000)` → `trema_ec_calibrate()`
- Прошивка отвечает `command_response`: `{"status": "DONE"}` или `{"status": "ERROR", "error_code": "calibration_failed"}`
- Калибровочные данные (offset/slope) хранятся на самом сенсоре (Trema EEPROM)
- Калибровка **не появляется** в периодической телеметрии

### Новая архитектура

```
Frontend (Vue wizard)
    │
    ├─ [1] POST /api/zones/{zone}/sensor-calibrations         → создать сессию
    │
    ├─ [2] POST /api/zones/{zone}/sensor-calibrations/{id}/point
    │       └─ Laravel → POST /commands (History-Logger)
    │                      └─ MQTT publish: calibrate(stage, reference_value)
    │                          └─ ESP32 → command_response: DONE / ERROR
    │       └─ Laravel сохраняет command_id и pending-status в sensor_calibrations
    │
    ├─ [3] existing command-status ingest / reconcile path
    │       └─ обновляет sensor_calibrations по terminal status команды
    │
    ├─ [4] Повтор шага 2 для stage 2
    │
    └─ [5] Frontend poll'ит calibration resource до terminal state
```

### Таблица `sensor_calibrations`

```sql
CREATE TABLE sensor_calibrations (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         INT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    node_channel_id INT NOT NULL REFERENCES node_channels(id) ON DELETE CASCADE,
    sensor_type     VARCHAR(16) NOT NULL CHECK (sensor_type IN ('ph', 'ec')),
    status          VARCHAR(32) NOT NULL DEFAULT 'started'
                    CHECK (status IN (
                        'started',
                        'point_1_pending',
                        'point_1_done',
                        'point_2_pending',
                        'completed',
                        'failed',
                        'cancelled'
                    )),

    -- Point 1
    point_1_reference   DECIMAL(12,4),    -- known value: pH units или TDS ppm
    point_1_command_id  UUID,
    point_1_sent_at     TIMESTAMPTZ,
    point_1_result      VARCHAR(16),      -- 'DONE' | 'ERROR'
    point_1_error       TEXT,

    -- Point 2
    point_2_reference   DECIMAL(12,4),
    point_2_command_id  UUID,
    point_2_sent_at     TIMESTAMPTZ,
    point_2_result      VARCHAR(16),
    point_2_error       TEXT,

    -- Metadata
    completed_at    TIMESTAMPTZ,
    calibrated_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
    notes           TEXT,
    meta            JSONB DEFAULT '{}',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sensor_cal_zone_type ON sensor_calibrations (zone_id, sensor_type, created_at DESC);
CREATE INDEX idx_sensor_cal_channel   ON sensor_calibrations (node_channel_id, status, created_at DESC);
```

**Статусы:**
- `started` — сессия создана, ни одна точка не выполнена
- `point_1_pending` — команда stage 1 отправлена, ждём terminal status
- `point_1_done` — первая точка калибровки выполнена
- `point_2_pending` — команда stage 2 отправлена, ждём terminal status
- `completed` — обе точки выполнены успешно
- `failed` — одна из точек вернула ERROR
- `cancelled` — пользователь отменил

### Namespace: `sensor_calibration` (настройки)

| Ключ | Default | Описание | Тип | Min | Max |
|------|---------|----------|-----|-----|-----|
| `ph_point_1_value` | 7.00 | pH буферного раствора для точки 1 | number | 1.0 | 14.0 |
| `ph_point_2_value` | 4.01 | pH буферного раствора для точки 2 | number | 1.0 | 14.0 |
| `ec_point_1_tds` | 1413 | TDS эталонного раствора для точки 1 (ppm) | integer | 100 | 10000 |
| `ec_point_2_tds` | 707 | TDS эталонного раствора для точки 2 (ppm) | integer | 50 | 10000 |
| `reminder_days` | 30 | Дней до напоминания о калибровке | integer | 7 | 365 |
| `critical_days` | 90 | Дней до критичного предупреждения | integer | 14 | 365 |
| `command_timeout_sec` | 10 | Таймаут MQTT команды калибровки (сек) | integer | 5 | 60 |
| `ph_reference_min` | 1.0 | Мин. допустимое значение pH буфера | number | 0.0 | 6.0 |
| `ph_reference_max` | 12.0 | Макс. допустимое значение pH буфера | number | 8.0 | 14.0 |
| `ec_tds_reference_max` | 10000 | Макс. допустимое TDS эталонного раствора (ppm) | integer | 1000 | 20000 |

---

## Фаза 1: БД — миграции, модели, каталог

### 1.1 Миграция: `system_automation_settings`

**Файл:** `backend/laravel/database/migrations/2026_03_14_120000_create_system_automation_settings.php`

```php
Schema::create('system_automation_settings', function (Blueprint $table) {
    $table->id();
    $table->string('namespace', 64)->unique();
    $table->jsonb('config')->default('{}');
    $table->unsignedBigInteger('updated_by')->nullable();
    $table->foreign('updated_by')->references('id')->on('users')->nullOnDelete();
    $table->timestamps();
});

// Seed 2 namespaces из каталога:
$catalog = SystemAutomationSettingsCatalog::allDefaults();
foreach ($catalog as $ns => $config) {
    DB::table('system_automation_settings')->insert([
        'namespace'  => $ns,
        'config'     => json_encode($config),
        'created_at' => now(),
        'updated_at' => now(),
    ]);
}
```

### 1.2 Миграция: `sensor_calibrations`

**Файл:** `backend/laravel/database/migrations/2026_03_14_120001_create_sensor_calibrations.php`

SQL-схема — см. выше. Таблица для истории калибровок сенсоров и привязки к `command_id`.

### 1.3 Миграция: расширение `zone_correction_configs`

**Файл:** `backend/laravel/database/migrations/2026_03_14_120002_extend_correction_config_with_pump_calibration.php`

```php
// Добавить секцию pump_calibration в resolved_config всех zone_correction_configs.
// JSONB merge: SET resolved_config = jsonb_set(resolved_config, '{pump_calibration}', '...')
// Только если секция ещё не существует (idempotent).
```

### 1.4 Модель `SystemAutomationSetting`

**Файл:** `backend/laravel/app/Models/SystemAutomationSetting.php`

```php
class SystemAutomationSetting extends Model
{
    protected $fillable = ['namespace', 'config', 'updated_by'];
    protected $casts    = ['config' => 'array'];

    public static function forNamespace(string $ns): array
    {
        return Cache::remember(
            "sys_auto_settings:{$ns}",
            300,
            fn () => static::where('namespace', $ns)->value('config')
                     ?? throw new \RuntimeException(
                         "system_automation_settings: namespace '{$ns}' not found, run migration"
                     ),
        );
    }

    public static function flushCache(string $ns): void
    {
        Cache::forget("sys_auto_settings:{$ns}");
    }
}
```

### 1.5 Модель `SensorCalibration`

**Файл:** `backend/laravel/app/Models/SensorCalibration.php`

```php
class SensorCalibration extends Model
{
    protected $fillable = [
        'zone_id', 'node_channel_id', 'sensor_type', 'status',
        'point_1_reference', 'point_1_command_id', 'point_1_sent_at', 'point_1_result', 'point_1_error',
        'point_2_reference', 'point_2_command_id', 'point_2_sent_at', 'point_2_result', 'point_2_error',
        'completed_at', 'calibrated_by', 'notes', 'meta',
    ];

    protected $casts = [
        'point_1_reference' => 'float',
        'point_2_reference' => 'float',
        'point_1_sent_at'   => 'datetime',
        'point_2_sent_at'   => 'datetime',
        'completed_at'      => 'datetime',
        'meta'              => 'array',
    ];

    public function isTerminal(): bool
    {
        return in_array($this->status, ['completed', 'failed', 'cancelled'], true);
    }

    public function zone()       { return $this->belongsTo(Zone::class); }
    public function nodeChannel() { return $this->belongsTo(NodeChannel::class); }
    public function user()       { return $this->belongsTo(User::class, 'calibrated_by'); }
}
```

### 1.6 Каталог `SystemAutomationSettingsCatalog`

**Файл:** `backend/laravel/app/Services/SystemAutomationSettingsCatalog.php`

Содержит **2 namespace** с дефолтами и field catalog (по образцу `ZoneCorrectionConfigCatalog`):
- `pump_calibration` — 11 полей
- `sensor_calibration` — 10 полей

Методы:
- `allDefaults(): array<string, array>` — все namespace с дефолтами
- `defaults(string $ns): array` — дефолты одного namespace
- `fieldCatalog(string $ns): array` — описание полей для UI
- `validate(string $ns, array $config): array` — валидация по field catalog

### 1.7 Секция `pump_calibration` в `ZoneCorrectionConfigCatalog`

`ZoneCorrectionConfigCatalog` не должен получать дефолты `pump_calibration`.

Допустимые варианты:
- добавить schema/field metadata для секции `pump_calibration`, без runtime default values.

Runtime-логика остаётся такой:
`zone_correction_configs.resolved_config.pump_calibration[ключ]` → fallback в `system_automation_settings['pump_calibration'][ключ]`.

Zone-level override **нужен в первой итерации**. Значит write-path должен быть явным:
- Laravel сохраняет override в `zone_correction_configs` через существующий zone correction config service / controller path;
- UI зоны получает отдельную секцию/форму для `pump_calibration` override;
- `reset` для зоны очищает только override-ключи секции `pump_calibration`, не трогая system-level namespace.

---

## Фаза 2: Laravel API

### 2.1 Контроллер системных настроек

**Файл:** `backend/laravel/app/Http/Controllers/SystemAutomationSettingsController.php`

```
GET  /api/system/automation-settings                    → index (все namespaces)
GET  /api/system/automation-settings/{namespace}        → show
PUT  /api/system/automation-settings/{namespace}        → update (partial merge)
POST /api/system/automation-settings/{namespace}/reset  → reset к дефолтам из каталога
```

- Требует роль `admin`.
- Ответ включает `meta.field_catalog` и `meta.defaults`.
- `update` принимает partial config (merge с текущими). Валидация по field catalog.
- `reset` — UPDATE config на defaults (НЕ delete).
- `Cache::forget` после каждого update/reset.

### 2.2 Контроллер калибровки сенсоров

**Файл:** `backend/laravel/app/Http/Controllers/SensorCalibrationController.php`

```
GET  /api/zones/{zone}/sensor-calibrations              → index (история)
GET  /api/zones/{zone}/sensor-calibrations/status       → overview всех сенсоров зоны
GET  /api/zones/{zone}/sensor-calibrations/{id}         → show (для polling)
POST /api/zones/{zone}/sensor-calibrations              → create (начать сессию)
POST /api/zones/{zone}/sensor-calibrations/{id}/point   → submit calibration point
POST /api/zones/{zone}/sensor-calibrations/{id}/cancel  → отменить сессию
```

#### `index` — история калибровок

```php
// GET /api/zones/{zone}/sensor-calibrations?sensor_type=ph&limit=20
// Возвращает пагинированный список sensor_calibrations, newest first.
```

#### `status` — обзор по всем сенсорам зоны

```php
// GET /api/zones/{zone}/sensor-calibrations/status
// Для каждого sensor channel (pH, EC) в зоне возвращает:
// - node_channel_id, channel_uid, sensor_type
// - last_calibrated_at (MAX completed_at WHERE status='completed')
// - days_since_calibration
// - calibration_status: 'ok' | 'warning' | 'critical' | 'never'
//   (вычисляется по reminder_days и critical_days из system_automation_settings)
// - has_active_session (есть ли незавершённая калибровка)
```

#### `create` — начать сессию калибровки

```php
// POST /api/zones/{zone}/sensor-calibrations
// Body: { "node_channel_id": 123, "sensor_type": "ph" }
//
// Валидация:
// - node_channel_id принадлежит зоне
// - sensor_type ∈ ['ph', 'ec']
// - нет активной сессии для этого channel (status NOT IN terminal)
//
// Создаёт запись status='started', calibrated_by=auth()->id.
// Возвращает: sensor_calibration + defaults (reference values) из settings.
```

#### `point` — отправить калибровочную точку

```php
// POST /api/zones/{zone}/sensor-calibrations/{id}/point
// Body: { "stage": 1, "reference_value": 7.0 }
//
// Валидация:
// - stage ∈ [1, 2]
// - stage 1: калибровка в status 'started'
// - stage 2: калибровка в status 'point_1_done'
// - reference_value в допустимом диапазоне (из sensor_calibration settings)
//
// Действие:
// 1. Найти node_uid и channel_uid через node_channel_id
// 2. Отправить canonical POST /commands в history-logger:
//    {
//      "greenhouse_uid": "...",
//      "zone_id": 123,
//      "node_uid": "...",
//      "channel": "ph_sensor",
//      "cmd": "calibrate",
//      "params": { "stage": 1, "known_ph": 7.0 },
//      "source": "api"
//    }
// 3. Сохранить command_id в point_N_command_id и перевести запись в
//    status='point_1_pending' или 'point_2_pending'
// 4. Existing command-status ingest / reconcile path обновляет:
//    - point_N_result, point_N_error
//    - status → 'point_1_done' | 'completed' | 'failed'
//    - completed_at = now() если completed/failed
// 5. Вернуть запись сразу после enqueue; frontend делает polling по show endpoint
```

#### `cancel` — отменить

```php
// POST /api/zones/{zone}/sensor-calibrations/{id}/cancel
// Устанавливает status='cancelled'. Не трогает node — ничего физически не отменяется.
```

### 2.3 Обновление `ZonePumpCalibrationsController`

**Файл:** `backend/laravel/app/Http/Controllers/ZonePumpCalibrationsController.php`

```php
// БЫЛО (строка 126):
'ml_per_sec' => ['required', 'numeric', 'min:0.01', 'max:20'],

// СТАЛО:
$s = SystemAutomationSetting::forNamespace('pump_calibration');
$data = $request->validate([
    'ml_per_sec' => ['required', 'numeric', "min:{$s['ml_per_sec_min']}", "max:{$s['ml_per_sec_max']}"],
]);
```

### 2.4 Маршруты

**Файл:** `backend/laravel/routes/api.php`

```php
// System settings
Route::prefix('system/automation-settings')->middleware('can:admin')->group(function () {
    Route::get('/', [SystemAutomationSettingsController::class, 'index']);
    Route::get('{namespace}', [SystemAutomationSettingsController::class, 'show']);
    Route::put('{namespace}', [SystemAutomationSettingsController::class, 'update']);
    Route::post('{namespace}/reset', [SystemAutomationSettingsController::class, 'reset']);
});

// Sensor calibration
Route::prefix('zones/{zone}/sensor-calibrations')->group(function () {
    Route::get('/', [SensorCalibrationController::class, 'index']);
    Route::get('status', [SensorCalibrationController::class, 'status']);
    Route::get('{calibration}', [SensorCalibrationController::class, 'show']);
    Route::post('/', [SensorCalibrationController::class, 'create']);
    Route::post('{calibration}/point', [SensorCalibrationController::class, 'point']);
    Route::post('{calibration}/cancel', [SensorCalibrationController::class, 'cancel']);
});
```

---

## Фаза 3: History-Logger — без нового publish endpoint

### 3.1 Канонический transport

- Для sensor calibration используется существующий `POST /commands`.
- Специализированный endpoint вида `POST /zones/{zone_id}/calibrate-sensor` не добавляется,
  чтобы не ломать архитектурный инвариант publish path.
- Если текущая валидация команд в history-logger недостаточна для `cmd="calibrate"`,
  она расширяется внутри существующего command validation / publish flow, а не отдельным API.

### 3.2 Валидация и ожидание результата

- Laravel валидирует `reference_value` по `sensor_calibration` settings до отправки команды.
- History-logger сохраняет coarse transport validation для payload `calibrate`.
- Terminal result команды не ждётся синхронно в HTTP-ответе Laravel; используется существующий DB-first
  status flow (`commands` + ingest/reconcile).
- `command_timeout_sec` остаётся source-of-truth в `system_automation_settings['sensor_calibration']`
  и применяется в Laravel/reconcile logic; не оставлять hardcoded `10`.
- Для sensor calibration успешным terminal status считается только `DONE`.
  Все остальные terminal статусы (`NO_EFFECT`, `ERROR`, `INVALID`, `BUSY`, `TIMEOUT`, `SEND_FAILED`)
  маппятся в `sensor_calibrations.status='failed'`.

---

## Фаза 4: Python AE — чтение pump_calibration из БД

### 4.1 SystemSettingsLoader

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/system_settings_loader.py`

```python
class SystemSettingsLoader:
    """
    Загружает system_automation_settings из PostgreSQL.
    Кэш с TTL 60с. Нет hardcoded fallback.
    """

    def __init__(self, pool):
        self._pool = pool
        self._cache: dict[str, dict] = {}
        self._last_loaded_at: float = 0
        self._refresh_interval_sec = 60

    async def get(self, namespace: str) -> dict:
        await self._maybe_refresh()
        if namespace not in self._cache:
            raise RuntimeError(
                f"system_automation_settings: namespace '{namespace}' not found"
            )
        return self._cache[namespace]

    async def resolve(self, namespace: str, key: str,
                      zone_config: Mapping | None = None) -> Any:
        """zone override → system setting. Нет hardcoded fallback."""
        if zone_config:
            section = zone_config.get(namespace)
            if isinstance(section, Mapping) and key in section:
                return section[key]
        sys = await self.get(namespace)
        if key not in sys:
            raise KeyError(f"system_automation_settings[{namespace}].{key} not found")
        return sys[key]

    async def _maybe_refresh(self):
        now = time.monotonic()
        if now - self._last_loaded_at < self._refresh_interval_sec:
            return
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT namespace, config FROM system_automation_settings"
            )
        self._cache = {r["namespace"]: json.loads(r["config"]) if isinstance(r["config"], str) else r["config"] for r in rows}
        self._last_loaded_at = now
```

Регистрировать в `lifespan` (`ae3lite/runtime/app.py`).

### 4.2 correction_planner.py — удаление констант

**Файл:** `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py`

**Удалить:**
```python
_MIN_DOSE_MS = 50  # строка 37 → в correction_config.pump_calibration
```

**Заменить `_dose_ml_to_ms()`:**
```python
def _dose_ml_to_ms(dose_ml: float, calibration: Mapping, correction_config: Mapping) -> int:
    pump_cal = correction_config.get("pump_calibration", {})
    min_dose_ms = int(pump_cal["min_dose_ms"])
    ml_min = float(pump_cal["ml_per_sec_min"])
    ml_max = float(pump_cal["ml_per_sec_max"])

    raw = calibration.get("ml_per_sec")
    if raw is None:
        raise PlannerConfigurationError("ml_per_sec not found in calibration")
    ml_per_sec = float(raw)
    if not (ml_min <= ml_per_sec <= ml_max):
        raise PlannerConfigurationError(
            f"ml_per_sec={ml_per_sec} out of range [{ml_min}, {ml_max}]"
        )

    duration_ms = int(dose_ml / ml_per_sec * 1000)
    if duration_ms < min_dose_ms:
        return 0
    return duration_ms
```

**Вызывающие места:** строки 244 и 288 — добавить `correction_config` параметр.

### 4.3 water_flow.py — pump calibration settings из БД

**Файл:** `backend/services/common/water_flow.py`

В `calibrate_pump()` (строки 923-1216):

```python
async def calibrate_pump(...):
    s = await _load_settings("pump_calibration")
    if not (s["calibration_duration_min_sec"] <= duration_sec <= s["calibration_duration_max_sec"]):
        raise ValueError(
            f"duration_sec {duration_sec} out of range "
            f"[{s['calibration_duration_min_sec']}, {s['calibration_duration_max_sec']}]"
        )
    # ...
    if not (s["ml_per_sec_min"] <= ml_per_sec <= s["ml_per_sec_max"]):
        raise ValueError(
            f"ml_per_sec {ml_per_sec} out of range [{s['ml_per_sec_min']}, {s['ml_per_sec_max']}]"
        )
    quality_score = s["quality_score_with_k"] if k_ms_per_ml_l is not None else s["quality_score_basic"]
```

Удалить `quality_score = 0.9 if ... else 0.75` (строка 1096).

```python
async def _load_settings(namespace: str) -> dict:
    """Загрузка из system_automation_settings. Raise если не найден."""
    rows = await fetch(
        "SELECT config FROM system_automation_settings WHERE namespace = $1",
        namespace,
    )
    if not rows:
        raise RuntimeError(f"system_automation_settings: namespace '{namespace}' not found")
    config = rows[0]["config"]
    return json.loads(config) if isinstance(config, str) else config
```

---

## Фаза 5: Frontend

### 5.1 Страница системных настроек (новая)

**Файл:** `backend/laravel/resources/js/Pages/SystemSettings.vue`

Страница доступна только admin. **2 таба**:

| Tab | Namespace | Полей |
|-----|-----------|-------|
| Калибровка насосов | `pump_calibration` | 11 |
| Калибровка сенсоров | `sensor_calibration` | 10 |

**UI паттерн:**
- По образцу `CorrectionConfigForm.vue`: секции с полями, label, описание, input.
- Field catalog из API (`meta.field_catalog`) — рендерить динамически.
- Кнопка «Сбросить к дефолтам» для каждого namespace.
- Хлебные крошки: Система → Настройки калибровки.
- Toast notification при сохранении.
- Показывать текущее значение vs дефолт (highlight если отличается).

### 5.1.1 Zone-level override для pump calibration

Zone automation UI получает отдельный editor для `resolved_config.pump_calibration`:
- размещение: в зоне, рядом с `PumpCalibrationsPanel` / correction config;
- поля: тот же catalog, что у `pump_calibration`, но значения показываются как `zone override or inherited`;
- действия: `Сохранить override`, `Сбросить к системным значениям`;
- при пустом override UI явно показывает, что используется system-level namespace.

### 5.2 Компонент калибровки сенсора (wizard)

**Файл:** `backend/laravel/resources/js/Components/SensorCalibrationWizard.vue`

Пошаговый wizard для калибровки pH или EC сенсора:

**Step 1: Подготовка**
- Показать: тип сенсора, канал, узел
- Показать: рекомендуемые значения буфера из settings (ph_point_1_value, ph_point_2_value)
- Кнопка «Начать калибровку»
- → POST create → получить calibration ID

**Step 2: Point 1**
- Инструкция: «Поместите датчик в буферный раствор pH {settings.ph_point_1_value}»
- Input для ввода reference value (предзаполнен из settings)
- Кнопка «Калибровать точку 1»
- → POST point (stage=1) → показать pending state и `command_id`
- wizard poll'ит `GET /api/zones/{zone}/sensor-calibrations/{id}` до terminal result
- Если ERROR/failed — показать ошибку, предложить повторить или отменить

**Step 3: Point 2**
- Инструкция: «Поместите датчик в буферный раствор pH {settings.ph_point_2_value}»
- Аналогично step 2

**Step 4: Результат**
- Показать: обе точки выполнены, дата, кто калибровал
- Кнопка «Готово»

Для EC — аналогично, но с TDS ppm вместо pH.

### 5.3 Панель статуса калибровок на странице зоны

**Файл:** `backend/laravel/resources/js/Components/SensorCalibrationStatus.vue`

Компонент для отображения на странице зоны (рядом с PumpCalibrationsPanel):

- Список sensor channels (pH, EC) зоны
- Для каждого: последняя калибровка, дней назад, статус (ok/warning/critical/never)
- Цветовой индикатор: зелёный (ok), жёлтый (warning), красный (critical), серый (never)
- Кнопка «Калибровать» → открывает SensorCalibrationWizard
- Кнопка «История» → modal со списком прошлых калибровок

### 5.4 Обновление PumpCalibrationsPanel.vue

**Файл:** `backend/laravel/resources/js/Components/PumpCalibrationsPanel.vue`

- `> 30` → `> settings.age_warning_days`
- `min="0.01" max="20"` → `:min="settings.ml_per_sec_min" :max="settings.ml_per_sec_max"`
- Получать `settings` из Inertia props `pumpCalibrationSettings`.

### 5.5 Обновление PumpCalibrationModal.vue

- `min="1" max="120"` → `:min` / `:max` из settings

### 5.6 Обновление usePumpCalibration.ts

- `duration_sec = ref(20)` → `ref(settings.default_run_duration_sec)`
- `min: 1, max: 120` → из settings.

### 5.7 Composables

**Файл:** `backend/laravel/resources/js/composables/useSystemSettings.ts`

```typescript
export function useSystemSettings() {
    async function getAll(): Promise<Record<string, SettingsNamespace>>
    async function getNamespace(ns: string): Promise<SettingsNamespace>
    async function updateNamespace(ns: string, config: Record<string, any>): Promise<void>
    async function resetNamespace(ns: string): Promise<void>
}
```

**Файл:** `backend/laravel/resources/js/composables/useSensorCalibration.ts`

```typescript
export function useSensorCalibration(zoneId: number) {
    function fetchStatus(): Promise<SensorCalibrationOverview[]>
    function fetchHistory(sensorType: string, limit?: number): Promise<SensorCalibration[]>
    function getCalibration(calibrationId: number): Promise<SensorCalibration>
    function startCalibration(nodeChannelId: number, sensorType: string): Promise<SensorCalibration>
    function submitPoint(calibrationId: number, stage: number, referenceValue: number): Promise<SensorCalibration>
    function cancelCalibration(calibrationId: number): Promise<void>
}
```

### 5.8 TypeScript типы

**Файл:** `backend/laravel/resources/js/types/SystemSettings.ts`

Интерфейсы для `pump_calibration` и `sensor_calibration` namespaces.

**Файл:** `backend/laravel/resources/js/types/SensorCalibration.ts`

```typescript
interface SensorCalibration {
    id: number
    zone_id: number
    node_channel_id: number
    sensor_type: 'ph' | 'ec'
    status: 'started' | 'point_1_pending' | 'point_1_done' | 'point_2_pending' | 'completed' | 'failed' | 'cancelled'
    point_1_reference: number | null
    point_1_command_id: string | null
    point_1_sent_at: string | null
    point_1_result: 'DONE' | 'ERROR' | null
    point_1_error: string | null
    point_2_reference: number | null
    point_2_command_id: string | null
    point_2_sent_at: string | null
    point_2_result: 'DONE' | 'ERROR' | null
    point_2_error: string | null
    completed_at: string | null
    calibrated_by: number | null
    notes: string | null
    created_at: string
}

interface SensorCalibrationOverview {
    node_channel_id: number
    channel_uid: string
    sensor_type: 'ph' | 'ec'
    last_calibrated_at: string | null
    days_since_calibration: number | null
    calibration_status: 'ok' | 'warning' | 'critical' | 'never'
    has_active_session: boolean
}
```

### 5.9 Маршруты Inertia

**Файл:** `backend/laravel/routes/web.php`

```php
Route::get('/system/settings', fn () => Inertia::render('SystemSettings'))
    ->middleware('can:admin')
    ->name('system.settings');
```

Добавить в zone show page:
```php
'pumpCalibrationSettings' => SystemAutomationSetting::forNamespace('pump_calibration'),
'sensorCalibrationSettings' => SystemAutomationSetting::forNamespace('sensor_calibration'),
```

---

## Фаза 6: Тесты

### 6.1 Laravel тесты

**Файл:** `backend/laravel/tests/Feature/SystemAutomationSettingsControllerTest.php`

- `test_index_returns_all_namespaces`
- `test_show_returns_seeded_defaults`
- `test_update_validates_field_ranges`
- `test_update_merges_partial_config`
- `test_reset_restores_catalog_defaults`
- `test_non_admin_cannot_update` (403)
- `test_unknown_namespace_returns_404`

**Файл:** `backend/laravel/tests/Feature/SensorCalibrationControllerTest.php`

- `test_create_calibration_session`
- `test_create_prevents_duplicate_active_session`
- `test_submit_point_1_enqueues_command_and_marks_pending`
- `test_submit_point_2_enqueues_command_and_marks_pending`
- `test_submit_point_2_without_point_1_fails`
- `test_cancel_sets_status_cancelled`
- `test_status_returns_overview_for_all_sensors`
- `test_status_shows_warning_for_old_calibration`
- `test_show_returns_current_pending_or_terminal_state`
- `test_index_returns_history_newest_first`
- `test_command_terminal_ingest_marks_calibration_completed_or_failed`
- `test_non_done_terminal_command_statuses_map_to_failed`

**Обновить:** `ZonePumpCalibrationsControllerTest.php`
- `test_update_uses_dynamic_ml_per_sec_range_from_system_settings`

### 6.2 Python AE тесты

**Файл:** `backend/services/automation-engine/tests/test_system_settings_loader.py`

- `test_get_returns_namespace_config`
- `test_get_raises_on_missing_namespace`
- `test_resolve_zone_override_wins`
- `test_resolve_system_setting_returned`
- `test_resolve_raises_on_missing_key`
- `test_cache_refresh_interval`

**Обновить:** `test_ae3lite_correction_planner.py`
- `test_dose_ml_to_ms_uses_config_min_dose_ms`
- `test_dose_ml_to_ms_uses_config_ml_per_sec_range`
- `test_dose_ml_to_ms_raises_without_pump_calibration_in_config`

### 6.3 Python history-logger тесты

**Обновить:** `backend/services/common/test_water_flow.py`
- `test_calibrate_pump_validates_ml_per_sec_from_db`
- `test_calibrate_pump_uses_quality_scores_from_db`

### 6.4 Документация

- Обновить `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` для
  `system_automation_settings` и `sensor_calibrations`.
- Обновить `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md` и
  `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md` для новых Laravel API.
- Обновить описание zone correction config API/UI, чтобы `pump_calibration` zone override был частью контракта.
- Если в history-logger добавляется явная command validation для `cmd="calibrate"`,
  отразить это в `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` без ввода нового publish endpoint.

---

## Файлы для создания/изменения (summary)

### Новые файлы

| Файл | Описание |
|------|----------|
| `database/migrations/2026_03_14_120000_create_system_automation_settings.php` | Таблица + seed 2 namespace |
| `database/migrations/2026_03_14_120001_create_sensor_calibrations.php` | Таблица sensor_calibrations |
| `database/migrations/2026_03_14_120002_extend_correction_config_with_pump_calibration.php` | JSONB merge в zone_correction_configs |
| `app/Models/SystemAutomationSetting.php` | Модель системных настроек |
| `app/Models/SensorCalibration.php` | Модель калибровки сенсора |
| `app/Services/SystemAutomationSettingsCatalog.php` | Каталог: 2 namespace, defaults, field catalog |
| `app/Http/Controllers/SystemAutomationSettingsController.php` | CRUD контроллер настроек |
| `app/Http/Controllers/SensorCalibrationController.php` | Контроллер калибровки сенсоров |
| `app/Services/SensorCalibrationCommandService.php` | Формирование canonical `POST /commands` payload и запись pending state |
| `resources/js/Pages/SystemSettings.vue` | Страница настроек (2 таба) |
| `resources/js/Components/SensorCalibrationWizard.vue` | Wizard калибровки сенсора |
| `resources/js/Components/SensorCalibrationStatus.vue` | Панель статуса калибровок |
| `resources/js/composables/useSystemSettings.ts` | Composable настроек |
| `resources/js/composables/useSensorCalibration.ts` | Composable калибровки сенсоров |
| `resources/js/types/SystemSettings.ts` | TypeScript типы настроек |
| `resources/js/types/SensorCalibration.ts` | TypeScript типы калибровки |
| `ae3lite/infrastructure/system_settings_loader.py` | Загрузчик для AE |
| `tests/Feature/SystemAutomationSettingsControllerTest.php` | Laravel тесты настроек |
| `tests/Feature/SensorCalibrationControllerTest.php` | Laravel тесты калибровки |
| `tests/test_system_settings_loader.py` | AE тесты |

### Изменяемые файлы

| Файл | Что меняется |
|------|-------------|
| `app/Services/ZoneCorrectionConfigCatalog.php` | при необходимости только schema metadata для zone override, без defaults |
| `routes/api.php` | +4 маршрута system settings, +5 маршрутов sensor calibration |
| `routes/web.php` | +1 маршрут Inertia, +props в zone show |
| `app/Http/Controllers/ZonePumpCalibrationsController.php` | Динамические min/max из DB |
| `<zone correction config controller/service path>` | write/read/reset для `resolved_config.pump_calibration` zone override |
| `ae3lite/domain/services/correction_planner.py` | Удалить `_MIN_DOSE_MS`, `_dose_ml_to_ms()` → reads config |
| `ae3lite/runtime/app.py` | Регистрация SystemSettingsLoader |
| `services/common/water_flow.py` | `calibrate_pump()` → settings из БД |
| `<existing Laravel command status ingest/reconcile path>` | Маппинг terminal command status → `sensor_calibrations` |
| `services/history-logger/command_routes.py` | только если нужна явная validation/support для `cmd="calibrate"` внутри `POST /commands` |
| `resources/js/Components/PumpCalibrationsPanel.vue` | Динамические пороги из props |
| `resources/js/Components/PumpCalibrationModal.vue` | Динамические min/max |
| `resources/js/composables/usePumpCalibration.ts` | Дефолты из props |

---

## Ограничения

1. **НЕ трогать ESP32 firmware** — прошивочные дефолты остаются.
   Калибровочные данные сенсоров (offset/slope) хранятся на Trema EEPROM.
   Backend не имеет к ним доступа и не должен — он только инициирует калибровку.

2. **НЕ менять MQTT протокол** — используем существующую команду `calibrate`
   с параметрами `stage` + `known_ph` / `tds_value` (уже реализовано в firmware).

3. **НЕ менять формат `zone_correction_configs.resolved_config`** — только добавить
   новую секцию `pump_calibration`. Существующие секции не трогать.

4. **НЕ оставлять hardcoded fallback** — миграция seed'ит все дефолты.
   Код читает только из БД. Нет записи → `RuntimeError` (fail-loud).

5. **НЕ менять zone_correction_config presets** — секция `pump_calibration`
   не участвует в preset resolve.

6. **Sensor calibrations — только tracking + orchestration.** Backend не хранит offset/slope
   (это делает firmware). Backend отслеживает: когда, кто, какими буферами
   калибровал, и напоминает о необходимости перекалибровки.

7. **Terminal result sensor calibration не должен зависеть от синхронного HTTP wait.**
   Источник истины по статусу команды — `commands`/ingest/reconcile path, а не long-lived request Laravel → history-logger.

8. **Zone-level override обязателен.** `pump_calibration` должен редактироваться и на уровне системы,
   и на уровне зоны; при отсутствии override зона наследует system-level namespace.

---

## Критерии приёмки

1. **БД:** `system_automation_settings` создана, 2 namespace seed'ятся миграцией.
   `sensor_calibrations` создана.
2. **Нет pump calibration констант в коде:** `_MIN_DOSE_MS`, hardcoded ml_per_sec ranges,
   quality scores — удалены. `grep` → 0 совпадений.
3. **System settings API:** Все 4 эндпоинта отвечают. Field catalog в meta.
4. **Sensor calibration API:** create/show/index/status/point/cancel работают.
   Команда публикуется через canonical `POST /commands`, результат попадает в `sensor_calibrations`.
5. **Frontend settings:** Страница `/system/settings` — 2 таба, все поля, валидация, reset.
6. **Frontend zone override:** в зоне есть editor для `pump_calibration`, поддерживающий inheritance и reset override.
7. **Frontend wizard:** SensorCalibrationWizard — 2-step wizard, отправка команды, отображение результата.
8. **Frontend status:** SensorCalibrationStatus на странице зоны — статус калибровки с цветовыми индикаторами.
9. **AE:** `correction_planner._dose_ml_to_ms()` читает из `correction_config.pump_calibration`.
10. **HL:** `calibrate_pump()` валидирует по настройкам из БД.
11. **Согласованность:** `ml_per_sec_max` — одно значение из одного источника.
12. **Fail-loud:** При отсутствии namespace → RuntimeError/500.
13. **Нет нового history-logger publish endpoint:** sensor calibration идёт через `POST /commands`.
14. **Terminal mapping:** для sensor calibration только `DONE` считается успехом; любой другой terminal status завершает сессию как `failed`.
15. **Тесты:** Все существующие проходят. Новые тесты покрывают оба направления.

---

## Порядок выполнения

```
Фаза 1 (БД: миграции + модели + каталог)  ← первая
    ↓
Фаза 2 (Laravel API: system settings + sensor calibration controllers/services)  ← зависит от Ф1
  +
Фаза 3 (History-Logger: reuse POST /commands, optional validation hardening)  ← параллельно с Ф2
    ↓
Фаза 4 (AE: SystemSettingsLoader + correction_planner + water_flow)  ← зависит от Ф1
    ↓
Фаза 5 (Frontend: settings page + async wizard + status + обновление компонентов)  ← зависит от Ф2, Ф3
    ↓
Фаза 6 (Тесты + doc_ai contract updates)  ← финальная проверка
```

**Объём:** ~19 новых файлов, ~12 изменяемых, 3 миграции.

---

## Документы для чтения перед началом

1. `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md` — архитектура backend
2. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
3. `backend/laravel/app/Services/ZoneCorrectionConfigCatalog.php` — образец catalog pattern
4. `backend/laravel/app/Services/ZoneCorrectionConfigService.php` — образец CRUD сервиса
5. `backend/laravel/resources/js/Components/CorrectionConfigForm.vue` — образец UI формы настроек
6. `backend/laravel/app/Http/Controllers/ZonePumpCalibrationsController.php` — существующий CRUD насосов
7. `backend/services/history-logger/command_routes.py:1309-1345` — паттерн calibrate-pump endpoint
8. `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md:312-323` — MQTT calibrate command
9. `firmware/nodes/ph_node/main/ph_node_framework_integration.c:252-345` — firmware calibrate handler
