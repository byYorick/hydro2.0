# EFFECTIVE_TARGETS_SPEC.md
# Спецификация Effective Targets для контроллеров зон

Документ описывает формальную спецификацию **effective-targets** — структурированных целевых значений и параметров управления для зон выращивания.

Актуализация authority / AE3 (2026-03-24):
- effective-targets остаются канонической бизнес-моделью Laravel;
- automation-engine в runtime использует direct SQL read-model и не зависит от runtime вызовов `/api/internal/effective-targets/*`;
- структура effective-targets используется как эталон семантики для SQL parity.

Актуализация канона pH/EC targets (2026-03-27):
- `targets.ph.target|min|max` и `targets.ec.target|min|max` берутся только из активной recipe phase / phase snapshot grow cycle;
- `cycle.phase_overrides`, `cycle.manual_overrides` и `zone.logic_profile` не имеют права переопределять canonical `pH/EC target|min|max`;
- zone automation UI показывает эти значения как readonly derived fields, а не как редактируемые runtime-настройки.

Актуализация PID authority для AE3 (2026-07-20):
- nested `targets.ph.controller` / `targets.ec.controller` (Kp/Ki/Kd/deadband/max_dose/…)
  в схеме effective-targets — **legacy/документальный** контракт Laravel-модели;
  **AE3 runtime их не читает** как source of truth и **не** должен получать
  новые поля «второго редактора»;
- **канон AE3 (единственный runtime path):**

  | Параметр | Source of truth |
  |----------|-----------------|
  | target pH/EC | recipe phase only |
  | kp/ki/kd, dead/close/far | `zone.pid.{ph,ec}` |
  | min_interval_sec, max_dose_ml, max_integral, derivative_filter_alpha, observe | `zone.correction.controllers.*` |
  | process gains / transport_delay / settle | `zone.process_calibration.*` |
  | min/max_dose_ms, ml_per_sec | pump_calibration |

- `controllers.kp/ki/kd` при наличии `zone.pid` — fallback only (LiveEdit скрывает);
- см. `PID_CONFIG_REFERENCE.md` §0.

Актуализация per-phase EC и day/night (2026-04-13; **переписано 2026-07-22**):
- prepare owner больше **не** `target_ec_prepare` / `npk_ec_share` — канон: water-baseline +
  кумулятивные `T_*` + sequential pipeline (см. §9);
- AE3 выбирает active EC target по pipeline step (`T_ca` / `T_ca_mg` / … / `T_full`), не по
  «NPK share vs full»;
- irrigation: только pH; post-irrigation chemistry (`irrig_recirc`) удалена;
- при `day_night_enabled=true` night `target_ec` пересчитывает `nutrient_budget` и `T_*`
  от `(target_ec_night − water_ec)` — см. §10;
- compiled bundle обязан пересчитываться при `advancePhase`/`setPhase`/`changeRecipeRevision` (см. `RECIPE_ENGINE_FULL.md` §3.3).

Актуализация освещения day/night + гарантированный OFF (2026-07-08, этап A `AGRO_AUTONOMY_MASTER_PLAN.md` §A.1):
- в `targets.lighting` для режима `SCHEDULE` канонические поля фотопериода: `on_time`, `off_time`, `brightness` (день), `brightness_night` (ночь, default `0`);
- вне окна `[on_time, off_time)` целевая яркость = `brightness_night` (обычно `0` — гарантированное выключение);
- scheduler-dispatch `lighting_tick` передаёт в AE3 `desired_state` (`on`|`off`) и опционально `brightness_pct` — см. §4.4.1 и `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7.

**Связанные документы:**
- `RECIPE_ENGINE_FULL.md` — engine рецептов и фаз
- `ZONE_CONTROLLER_FULL.md` — контроллеры зон
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — модель данных

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 1. Назначение Effective Targets

**Effective targets** — это каноническая Laravel business/read-model семантика для контроллеров зон, которая определяет:
- Текущие целевые значения (pH, EC, температура и т.д.)
- Допустимые диапазоны отклонений
- Режимы работы систем (полив, освещение, климат)
- Расписания и параметры автоматизации

**Принцип работы:**
1. Laravel вычисляет effective targets на основе:
   - Активного grow cycle зоны
   - Текущей фазы цикла (VEG, FLOWER и т.д.)
   - Revision рецепта
   - Authority-конфигов `system.*`, `zone.*`, `cycle.*`
   - Operational facts и bind/calibration контекста зоны

2. Laravel и интеграции могут получать targets через REST API
3. Контроллеры AE3 используют эквивалентную семантику через SQL read-model и compiled bundles, а не через runtime HTTP к effective-targets API

Для `pH/EC` действует отдельное жёсткое правило:
- canonical source of truth для `target|min|max` — только active recipe phase;
- runtime merge допускается только для operational/execution-настроек подсистем, но не для chemical setpoints;
- отсутствие `ph/ec target` во phase snapshot считается конфигурационной ошибкой и должно fail-closed в correction runtime.

---

## 2. Источник effective targets

### 2.1. Laravel API Endpoint (diagnostics/integration)

**Endpoint:** `POST /api/internal/effective-targets/batch`

**Метод:** Batch получение targets для нескольких зон за один запрос.
Используется вне runtime path automation-engine.

**Request:**
```json
{
  "zone_ids": [1, 2, 3]
}
```

**Response:**
```json
{
  "1": {
    "cycle_id": 123,
    "phase": {
      "name": "VEG",
      "started_at": "2026-01-15T10:00:00Z",
      "due_at": "2026-02-15T10:00:00Z"
    },
    "targets": {
      "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
      "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
      "irrigation": {
        "mode": "SUBSTRATE",
        "interval_sec": 3600,
        "duration_sec": 60,
        "volume_ml": 2000
      },
      "lighting": {
        "mode": "SCHEDULE",
        "on_time": "06:00",
        "off_time": "22:00",
        "brightness": 80,
        "brightness_night": 0
      },
      "climate": {
        "temp_air": {"target": 24.0, "min": 22.0, "max": 26.0},
        "humidity_air": {"target": 65.0, "min": 60.0, "max": 70.0}
      }
    }
  },
  "2": {
    "cycle_id": null,
    "phase": null,
    "targets": {}
  }
}
```

### 2.2. Endpoint для одной зоны (diagnostics/integration)

**Endpoint:** `GET /api/internal/effective-targets/{zone_id}`

**Response:** Аналогично batch, но только для одной зоны.

---

## 3. Структура Effective Targets

### 3.1. Корневая структура

```typescript
interface EffectiveTargets {
  cycle_id: number | null;        // ID активного grow cycle (null если нет)
  phase: PhaseInfo | null;         // Информация о текущей фазе
  targets: Targets;                // Целевые значения и параметры
}
```

### 3.2. PhaseInfo

```typescript
interface PhaseInfo {
  name: string;              // Название фазы: VEG, FLOWER, HARVEST и т.д.
  started_at: string;        // ISO 8601 timestamp начала фазы
  due_at: string | null;     // ISO 8601 timestamp ожидаемого окончания (null если бесконечная)
  days_elapsed: number;      // Количество дней с начала фазы
  days_remaining: number | null; // Количество дней до окончания (null если бесконечная)
}
```

### 3.3. Targets (полная структура)

```typescript
interface Targets {
  // pH контроль
  ph?: PhTarget;

  // EC контроль
  ec?: EcTarget;

  // Температура раствора (solution_temp_c)
  solution_temp?: SolutionTempTarget;

  // Полив
  irrigation?: IrrigationTarget;

  // Освещение
  lighting?: LightingTarget;

  // Климат
  climate?: ClimateTarget;

  // Дозирование
  dosing?: DosingTarget;

  // Параметры correction cycle (стабилизация и интервалы)
  correction_timings?: CorrectionTimingsTarget;
}
```

---

## 4. Типы контроллеров и их targets

### 4.1. pH Controller

```typescript
interface PhTarget {
  target: number;     // Целевое значение pH (например, 6.0)
  min: number;        // Минимально допустимое значение (например, 5.8)
  max: number;        // Максимально допустимое значение (например, 6.2)

  // LEGACY / documentation-only для AE3 — НЕ authority.
  // AE3 НЕ читает эти поля. Не добавляйте сюда новые runtime-параметры:
  // тюнинг PID → zone.pid.*; caps/observe/max_integral → zone.correction.controllers.*;
  // gains/delays → zone.process_calibration.*; targets → recipe phase.
  // Опциональные параметры PID контроллера (исторический Laravel shape)
  controller?: {
    mode: "PID" | "ON_OFF";   // Режим контроллера
    Kp?: number;              // Пропорциональный коэффициент
    Ki?: number;              // Интегральный коэффициент
    Kd?: number;              // Дифференциальный коэффициент
    deadband?: number;        // Мертвая зона (например, 0.1)
    max_dose_ml?: number;     // Максимальная доза за раз (мл)
    cooldown_sec?: number;    // Время между дозированиями (сек)
  };
}
```

**Пример:**
```json
{
  "ph": {
    "target": 6.0,
    "min": 5.8,
    "max": 6.2,
    "controller": {
      "mode": "PID",
      "Kp": 1.2,
      "Ki": 0.05,
      "Kd": 0.01,
      "deadband": 0.1,
      "max_dose_ml": 5.0,
      "cooldown_sec": 300
    }
  }
}
```

### 4.2. EC Controller

```typescript
interface EcTarget {
  target: number;     // Целевое значение EC (mS/cm)
  min: number;        // Минимально допустимое значение
  max: number;        // Максимально допустимое значение

  // LEGACY / documentation-only для AE3 (см. §4.1 / шапку документа):
  // AE3 НЕ читает эти поля как PID authority. Не расширять как runtime contract.
  // Опциональные параметры контроллера
  controller?: {
    mode: "PID" | "ON_OFF";
    Kp?: number;
    Ki?: number;
    Kd?: number;
    deadband?: number;
    max_dose_ml?: number;
    cooldown_sec?: number;
    ratio_a_b?: number;      // Соотношение A:B (например, 1.0 для 1:1)
  };
}
```

**Пример:**
```json
{
  "ec": {
    "target": 1.5,
    "min": 1.3,
    "max": 1.7,
    "controller": {
      "mode": "PID",
      "Kp": 0.8,
      "Ki": 0.03,
      "Kd": 0.005,
      "deadband": 0.1,
      "max_dose_ml": 10.0,
      "cooldown_sec": 600,
      "ratio_a_b": 1.0
    }
  }
}
```

### 4.2.1. Solution Temperature (solution_temp_c)

Пороги температуры **питательного раствора** (канал `solution_temp_c`, domain `temp_water`).
Источник — колонки фазы рецепта / snapshot `grow_cycle_phases`:
`solution_temp_target`, `solution_temp_min`, `solution_temp_max`.

```typescript
interface SolutionTempTarget {
  target: number;   // Целевая t° раствора (°C)
  min: number;      // Нижний порог алерта (°C)
  max: number;      // Верхний порог алерта (°C)
}
```

**Пример:**
```json
{
  "solution_temp": {
    "target": 20.0,
    "min": 18.0,
    "max": 22.0
  }
}
```

**Алерты (этап C.1 `AGRO_AUTONOMY_MASTER_PLAN.md`):**
- при устойчивом выходе `solution_temp_c` выше `max` N минут → `biz_solution_temp_high`;
- при устойчивом выходе ниже `min` N минут → `biz_solution_temp_low`;
- проверка выполняется в `history-logger` на ingest-пути телеметрии (env `SOLUTION_TEMP_ALERT_DELAY_MINUTES`, default `10`).

### 4.3. Irrigation Controller

```typescript
interface IrrigationTarget {
  mode: "SCHEDULE" | "SUBSTRATE" | "FLOOD_DRAIN" | "DWC" | "MANUAL";

  // Для режима SCHEDULE
  interval_sec?: number;      // Интервал между поливами (сек)
  duration_sec?: number;      // Длительность полива (сек)
  volume_ml?: number;         // Объем полива (мл)

  // Примечание (AE3-Lite): `volume_ml` в effective targets остаётся доменным полем;
  // автоматический перевод «мл → длительность насоса» в runtime AE3-Lite не реализован
  // (используйте `duration_sec` и калибровки насоса; см. также Laravel scheduler payload `duration_sec`).

  // Для режима SUBSTRATE (по влажности субстрата)
  soil_moisture_min?: number;  // Минимальная влажность (%)
  soil_moisture_max?: number;  // Максимальная влажность (%)

  // Расписание поливов (опционально)
  schedule?: string[];         // Время поливов ["08:00", "12:00", "18:00"]
}
```

**Пример (SCHEDULE):**
```json
{
  "irrigation": {
    "mode": "SCHEDULE",
    "interval_sec": 3600,
    "duration_sec": 60,
    "volume_ml": 2000,
    "schedule": ["08:00", "12:00", "18:00"]
  }
}
```

**Пример (SUBSTRATE):**
```json
{
  "irrigation": {
    "mode": "SUBSTRATE",
    "soil_moisture_min": 40.0,
    "soil_moisture_max": 60.0,
    "duration_sec": 30,
    "volume_ml": 1000
  }
}
```

### 4.4. Lighting Controller

```typescript
interface LightingTarget {
  mode: "SCHEDULE" | "MANUAL" | "PHOTOPERIOD";

  // Для режима SCHEDULE (канон фотопериода, этап A)
  on_time?: string;            // Время начала светового дня (HH:MM, например "06:00")
  off_time?: string;           // Время конца светового дня (HH:MM, например "22:00")
  brightness?: number;         // Целевая яркость внутри окна [on_time, off_time), % (0–100)
  brightness_night?: number;   // Целевая яркость вне окна; default 0 (выключено)

  // Для режима PHOTOPERIOD (legacy / альтернативное задание окна)
  photoperiod_hours?: number;  // Длительность светового дня (часы)
  sunrise_time?: string;       // Время "восхода" (HH:MM)
  start_time?: string;         // Алиас on_time (используется Laravel scheduler / LightingScheduleParser)

  // Дополнительные параметры
  dimming?: {
    enabled: boolean;
    sunrise_duration_min: number;  // Длительность плавного включения (мин)
    sunset_duration_min: number;   // Длительность плавного выключения (мин)
  };
}
```

#### 4.4.1. Окно фотопериода и целевая яркость

Для `mode="SCHEDULE"` effective targets задают **полусуточное окно** фотопериода:

| Поле | Семантика |
|------|-----------|
| `on_time` | Начало светового дня (включительно), формат `HH:MM` или `HH:MM:SS`, локальное время теплицы |
| `off_time` | Конец светового дня (исключительно), тот же формат |
| `brightness` | PWM/relay duty внутри окна `[on_time, off_time)`, диапазон `0..100` |
| `brightness_night` | PWM/relay duty **вне** окна; если не задан — **`0`** (свет выключен) |

**Правило разрешения яркости** (локальное время зоны / теплицы):

```
если now ∈ [on_time, off_time):
    target_brightness = brightness ?? 100
иначе:
    target_brightness = brightness_night ?? 0
```

Интервал `[on_time, off_time)` — полуоткрытый: в момент `on_time` свет **включается**, в момент `off_time` — **выключается** (целевая яркость переходит на `brightness_night`).

**Совместимость с существующим scheduler:**

- `LightingScheduleParser` может строить окно из `start_time` + `photoperiod_hours` или из строки `lighting_schedule` (`"06:00-22:00"`); при сборке effective targets Laravel **нормализует** их в канонические `on_time` / `off_time`.
- Поля `pwm_duty` / `brightness_pct` в snapshot — runtime-алиасы для AE3 planner; источник истины для scheduler-dispatch — `brightness` / `brightness_night` из effective targets.

#### 4.4.2. `lighting_tick`: desired_state ON/OFF

Задача AE3 `lighting_tick` (ingress `POST /zones/{id}/start-lighting-tick`) исполняет **один** переход состояния освещения, инициированный Laravel scheduler на **границе** окна фотопериода (`SchedulerCycleOrchestrator`: сравнение «внутри окна» между текущим и предыдущим cursor-tick).

| `desired_state` | Когда dispatch | Команда AE3 (целевое поведение, этап A) |
|-----------------|----------------|----------------------------------------|
| `"on"` | Вход в окно `[on_time, off_time)` (включая переход `off → on` в `on_time`) | `set_pwm {duty: brightness_pct}` или `set_relay {state: true}` |
| `"off"` | Выход из окна (переход `on → off` в `off_time`) | `set_pwm {duty: 0}` или `set_relay {state: false}` |

Поля dispatch-payload (см. `StartLightingTickRequest`, `ScheduleDispatcher.php`):

- `desired_state`: `"on"` \| `"off"`, default `"on"` (backward-compat для interval/time-spec без окна).
- `brightness_pct`: опционально `0..100`; при `desired_state="on"` — явная яркость тика; если не передано, AE3 резолвит из effective targets / day-night config; fallback `100`.

**Идемпотентность:** повторный tick с тем же `desired_state` и той же фактической яркостью на узле — no-op (`NO_EFFECT` допустим); граница окна dispatch'ится один раз на переход состояния.

**Пример (SCHEDULE + day/night):**
```json
{
  "lighting": {
    "mode": "SCHEDULE",
    "on_time": "06:00",
    "off_time": "22:00",
    "brightness": 80,
    "brightness_night": 0,
    "dimming": {
      "enabled": true,
      "sunrise_duration_min": 30,
      "sunset_duration_min": 30
    }
  }
}
```

### 4.5. Climate Controller

```typescript
interface ClimateTarget {
  // Температура воздуха
  temp_air?: {
    target: number;    // Целевая температура (°C)
    min: number;       // Минимальная (°C)
    max: number;       // Максимальная (°C)
  };

  // Влажность воздуха
  humidity_air?: {
    target: number;    // Целевая влажность (%)
    min: number;       // Минимальная (%)
    max: number;       // Максимальная (%)
  };

  // CO2
  co2?: {
    target: number;    // Целевой уровень CO2 (ppm)
    min: number;       // Минимальный (ppm)
    max: number;       // Максимальный (ppm)
  };

  // VPD (Vapor Pressure Deficit)
  vpd?: {
    target: number;    // Целевой VPD (kPa)
    min: number;       // Минимальный (kPa)
    max: number;       // Максимальный (kPa)
  };
}
```

**Пример:**
```json
{
  "climate": {
    "temp_air": {
      "target": 24.0,
      "min": 22.0,
      "max": 26.0
    },
    "humidity_air": {
      "target": 65.0,
      "min": 60.0,
      "max": 70.0
    },
    "co2": {
      "target": 1200,
      "min": 1000,
      "max": 1400
    },
    "vpd": {
      "target": 1.0,
      "min": 0.8,
      "max": 1.2
    }
  }
}
```

### 4.6. Dosing Controller

```typescript
interface DosingTarget {
  // Дозирование питательных веществ
  nutrients?: {
    a_ml_per_liter?: number;     // Компонент A (мл/л)
    b_ml_per_liter?: number;     // Компонент B (мл/л)
    ratio_a_b?: number;          // Соотношение A:B
  };

  // Дозирование pH
  ph_up_ml_per_unit?: number;    // Дозировка pH+ на единицу pH
  ph_down_ml_per_unit?: number;  // Дозировка pH- на единицу pH
}
```

**Пример:**
```json
{
  "dosing": {
    "nutrients": {
      "a_ml_per_liter": 2.5,
      "b_ml_per_liter": 2.5,
      "ratio_a_b": 1.0
    },
    "ph_up_ml_per_unit": 0.5,
    "ph_down_ml_per_unit": 0.5
  }
}
```

### 4.7. Correction Cycle Timings

**Назначение:** Параметры стабилизации и интервалов для correction cycle state machine.

**ВАЖНО:** pH/EC измерения валидны только при потоке через сенсор. Эти параметры управляют жизненным циклом активации/деактивации сенсорных нод и частотой коррекций.

```typescript
interface CorrectionTimingsTarget {
  // Время стабилизации после активации (для разных состояний)
  tank_fill_stabilization_sec: number;     // По умолчанию: 90
  tank_recirc_stabilization_sec: number;   // По умолчанию: 30
  irrigation_stabilization_sec: number;    // По умолчанию: 30
  irrig_recirc_stabilization_sec: number;  // По умолчанию: 30

  // Время ожидания после дозирования (mixing time)
  npk_mix_time_sec: number;                // По умолчанию: 120
  ph_mix_time_sec: number;                 // По умолчанию: 60
  ca_mg_mix_time_sec: number;              // По умолчанию: 90

  // Интервалы коррекции
  min_correction_interval_sec: number;     // По умолчанию: 300 (5 мин)

  // Максимальные попытки рециркуляции
  max_tank_recirc_attempts: number;        // По умолчанию: 5
  max_irrig_recirc_attempts: number;       // По умолчанию: 2

  // Timeout режимов (макс. время выполнения)
  tank_fill_timeout_sec: number;           // По умолчанию: 1800 (30 мин)
  tank_recirc_timeout_sec: number;         // По умолчанию: 3600 (1 час)
  irrigation_timeout_sec: number;          // По умолчанию: 600 (10 мин)
}
```

**Пример (с default значениями):**
```json
{
  "correction_timings": {
    "tank_fill_stabilization_sec": 90,
    "tank_recirc_stabilization_sec": 30,
    "irrigation_stabilization_sec": 30,
    "irrig_recirc_stabilization_sec": 30,
    "npk_mix_time_sec": 120,
    "ph_mix_time_sec": 60,
    "ca_mg_mix_time_sec": 90,
    "min_correction_interval_sec": 300,
    "max_tank_recirc_attempts": 5,
    "max_irrig_recirc_attempts": 2,
    "tank_fill_timeout_sec": 1800,
    "tank_recirc_timeout_sec": 3600,
    "irrigation_timeout_sec": 600
  }
}
```

**Пример (кастомизированный):**
```json
{
  "correction_timings": {
    "tank_fill_stabilization_sec": 120,
    "tank_recirc_stabilization_sec": 45,
    "irrigation_stabilization_sec": 60,
    "irrig_recirc_stabilization_sec": 45,
    "npk_mix_time_sec": 180,
    "ph_mix_time_sec": 90,
    "ca_mg_mix_time_sec": 120,
    "min_correction_interval_sec": 600,
    "max_tank_recirc_attempts": 10,
    "max_irrig_recirc_attempts": 3,
    "tank_fill_timeout_sec": 2400,
    "tank_recirc_timeout_sec": 5400,
    "irrigation_timeout_sec": 900
  }
}
```

**Описание параметров:**

**Стабилизация сенсоров:**
- `tank_fill_stabilization_sec` — время стабилизации при активации в TANK_FILLING (обычно больше, т.к. идет заливка)
- `tank_recirc_stabilization_sec` — время стабилизации в TANK_RECIRC (меньше, т.к. раствор уже смешан)
- `irrigation_stabilization_sec` — время стабилизации при активации для IRRIGATING
- `irrig_recirc_stabilization_sec` — время стабилизации в IRRIG_RECIRC

**Mixing time (время перемешивания):**
- `npk_mix_time_sec` — время ожидания после дозирования NPK для перемешивания
- `ph_mix_time_sec` — время ожидания после pH коррекции
- `ca_mg_mix_time_sec` — время ожидания после дозирования Ca/Mg/micro

**Интервалы и ограничения:**
- `min_correction_interval_sec` — минимальный интервал между коррекциями (предотвращает передозировку)
- `max_tank_recirc_attempts` — максимальное количество попыток достичь целей в TANK_RECIRC
- `max_irrig_recirc_attempts` — максимальное количество попыток в IRRIG_RECIRC

**Timeouts:**
- `tank_fill_timeout_sec` — максимальное время режима TANK_FILLING
- `tank_recirc_timeout_sec` — максимальное время TANK_RECIRC
- `irrigation_timeout_sec` — максимальное время IRRIGATING

**Применение в state machine:**

| Состояние | Используемый параметр стабилизации | Типы коррекций |
|-----------|-----------------------------------|----------------|
| **IDLE** | — | Нет коррекций |
| **TANK_FILLING** / `solution_fill` | `tank_fill_stabilization_sec` (90s) | Calcium only (`pump_b`), без pH; EC target = water-baseline `T_ca` (см. §9) |
| **TANK_RECIRC** / `prepare` | `tank_recirc_stabilization_sec` (30s) | interleaved Ca→pH→Mg→pH→NPK→pH→Micro→final pH; cumulative `T_*` (+ dilute-on-overshoot) |
| **READY** | — | Нет коррекций |
| **IRRIGATING** | `irrigation_stabilization_sec` (30s) | только pH; EC excluded (`needs_ec=false`) |
| **IRRIG_RECIRC** | — | **removed** (legacy; post-irrigation chemistry нет) |

**Логика применения:**
- После **активации** ноды ждут `*_stabilization_sec` перед разрешением коррекций
- После **дозирования** automation-engine ждет `*_mix_time_sec` перед следующей проверкой
- Между **коррекциями** выдерживается `min_correction_interval_sec`
- При превышении `max_*_recirc_attempts` или `*_timeout_sec` происходит принудительный переход

**Default значения:**
```json
{
  "tank_fill_stabilization_sec": 90,
  "tank_recirc_stabilization_sec": 30,
  "irrigation_stabilization_sec": 30,
  "irrig_recirc_stabilization_sec": 30,
  "npk_mix_time_sec": 120,
  "ph_mix_time_sec": 60,
  "ca_mg_mix_time_sec": 90,
  "min_correction_interval_sec": 300,
  "max_tank_recirc_attempts": 5,
  "max_irrig_recirc_attempts": 2,
  "tank_fill_timeout_sec": 1800,
  "tank_recirc_timeout_sec": 3600,
  "irrigation_timeout_sec": 600
}
```

**См. также:**
- `CORRECTION_CYCLE_SPEC.md` — полная спецификация correction cycle state machine
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` (секция 7.5) — команды activate/deactivate
- `ARCHITECTURE_FLOWS.md` — диаграммы потоков коррекций

---

## 5. Примеры использования

### 5.1. Automation-Engine получает targets

```python
from repositories.laravel_api_repository import LaravelApiRepository

repo = LaravelApiRepository()

# Получить targets для нескольких зон
targets = await repo.get_effective_targets_batch([1, 2, 3])

# Для зоны 1
zone_1_targets = targets["1"]

if zone_1_targets["cycle_id"] is None:
    # Нет активного цикла - пропускаем зону
    return

# Проверяем pH
ph_target = zone_1_targets["targets"].get("ph")
if ph_target:
    current_ph = await get_current_telemetry(zone_id=1, metric="PH")

    if current_ph < ph_target["min"]:
        # pH слишком низкий - дозировать pH+
        dose_ml = calculate_dose(current_ph, ph_target["target"])
        await send_command_dose_ph_up(zone_id=1, ml=dose_ml)
```

### 5.1b. Automation-Engine использует correction_timings

```python
from repositories.laravel_api_repository import LaravelApiRepository
from correction_cycle import CorrectionStateMachine

repo = LaravelApiRepository()

# Получить targets для зоны
targets = await repo.get_effective_targets(zone_id=1)

# Извлечь параметры стабилизации и таймингов
correction_timings = targets["targets"].get("correction_timings", {
    "tank_fill_stabilization_sec": 90,
    "tank_recirc_stabilization_sec": 30,
    "irrigation_stabilization_sec": 30,
    "irrig_recirc_stabilization_sec": 30,
    "npk_mix_time_sec": 120,
    "ph_mix_time_sec": 60,
    "ca_mg_mix_time_sec": 90,
    "min_correction_interval_sec": 300,
    "max_tank_recirc_attempts": 5,
    "max_irrig_recirc_attempts": 2,
    "tank_fill_timeout_sec": 1800,
    "tank_recirc_timeout_sec": 3600,
    "irrigation_timeout_sec": 600
})

# Инициализация state machine
state_machine = CorrectionStateMachine(
    zone_id=1,
    correction_timings=correction_timings
)

# Переход IDLE → TANK_FILLING
await state_machine.transition_to_tank_filling()

# Активация pH/EC нод с параметром стабилизации для TANK_FILLING
await send_command_activate_sensor_mode(
    zone_id=1,
    node_uid="nd-ph-1",
    stabilization_time_sec=correction_timings["tank_fill_stabilization_sec"]
)

# Control loop проверяет телеметрию
telemetry = await get_current_telemetry(zone_id=1, metric="PH")

# Проверяем флаги перед коррекцией
if telemetry.get("corrections_allowed") and telemetry.get("stable"):
    ph_target = targets["targets"]["ph"]

    if telemetry["value"] < ph_target["min"]:
        # Проверяем, прошло ли min_interval_sec с последней коррекции
        if state_machine.can_correct():
            dose_ml = calculate_dose(telemetry["value"], ph_target["target"])
            await send_command_dose_ph_up(zone_id=1, ml=dose_ml)
            state_machine.record_correction_time()
else:
    # Ещё стабилизируется - ждём
    current_state = state_machine.get_current_state()
    stabilization_param = f"{current_state.lower()}_stabilization_sec"
    expected_time = correction_timings.get(stabilization_param, 60)

    logger.info(f"Zone {zone_id} pH sensor stabilizing in {current_state}: "
                f"{telemetry.get('stabilization_progress_sec')}s / {expected_time}s")
```

### 5.2. Integration tooling использует targets

```python
# Получить targets для зоны вне runtime path automation-engine
targets = await repo.get_effective_targets(zone_id=1)

# Проверяем расписание полива
irrigation = targets["targets"].get("irrigation")
if irrigation and irrigation["mode"] == "SCHEDULE":
    schedule = irrigation.get("schedule", [])

    for time_str in schedule:
        # Запланировать задачу полива на указанное время
        await create_scheduler_task({
            "type": "IRRIGATION",
            "zone_id": 1,
            "scheduled_at": time_str,
            "params": {
                "duration_sec": irrigation["duration_sec"],
                "volume_ml": irrigation["volume_ml"]
            }
        })
```

### 5.3. Frontend отображает targets

```typescript
// Vue композабл для чтения effective targets через публичный zone API,
// а не через internal endpoint
export function useZoneTargets(zoneId: Ref<number>) {
  const targets = ref<EffectiveTargets | null>(null);

  async function fetchTargets() {
    const response = await axios.get(`/api/zones/${zoneId.value}/grow-cycle`);
    targets.value = response.data?.data?.effective_targets ?? null;
  }

  return { targets, fetchTargets };
}

// Использование в компоненте
const { targets } = useZoneTargets(zoneId);

// Отображение pH targets
<div v-if="targets?.ph">
  <span>pH Target: {{ targets.ph.target }}</span>
  <span>Range: {{ targets.ph.min }} - {{ targets.ph.max }}</span>
</div>
```

---

## 6. Вычисление effective targets

### 6.1. Источники данных

Laravel вычисляет effective targets на основе:

1. **GrowCycle** — активный цикл выращивания зоны
2. **RecipeRevision / GrowCyclePhase** — текущая ревизия рецепта и снапшот фазы
3. **Authority documents / compiled bundles** — `system.*`, `zone.*`, `cycle.*`
4. **Zone operational facts** — bindings, calibration status, readiness-related runtime facts

### 6.2. Алгоритм

```php
function computeEffectiveTargets(Zone $zone): array
{
    // 1. Найти активный grow cycle
    $cycle = $zone->activeGrowCycle();
    if (!$cycle) {
        return [
            'cycle_id' => null,
            'phase' => null,
            'targets' => []
        ];
    }

    // 2. Получить текущую фазу
    $phase = $cycle->currentPhase();
    if (!$phase) {
        return [...];
    }

    // 3. Загрузить recipe revision
    $revision = $cycle->recipeRevision;

    // 4. Извлечь targets из phase column
    $phaseData = $revision->{$phase->name . '_phase'};  // veg_phase, flower_phase и т.д.

    // 5. Merge с default значениями зоны
    $targets = array_merge(
        $zone->default_targets ?? [],
        $phaseData['targets'] ?? []
    );

    return [
        'cycle_id' => $cycle->id,
        'phase' => [
            'name' => $phase->name,
            'started_at' => $phase->started_at,
            'due_at' => $phase->due_at,
            'days_elapsed' => $phase->days_elapsed,
            'days_remaining' => $phase->days_remaining
        ],
        'targets' => $targets
    ];
}
```

### 6.3. Кэширование

**Важно:** Effective targets **НЕ кэшируются** постоянно, так как они могут меняться:
- При смене фазы grow cycle
- При обновлении recipe revision
- При изменении базовых параметров зоны

Python сервисы должны регулярно обновлять targets (например, каждые 15-60 секунд).

---

## 7. Валидация targets

### 7.1. Обязательные проверки

При вычислении effective targets Laravel выполняет валидацию:

1. **Диапазоны значений:**
   - `min <= target <= max`
   - Все числовые значения положительные (где применимо)

2. **Типы данных:**
   - `target`, `min`, `max` — числа
   - `mode` — строка из допустимых значений
   - Времена в формате "HH:MM"

3. **Логическая корректность:**
   - Для `irrigation.schedule` — времена в хронологическом порядке
   - Для `lighting` (режим `SCHEDULE`) — `on_time` < `off_time`; `brightness` и `brightness_night` ∈ `[0, 100]`
   - Для `controller.ratio_a_b` — не равно 0

### 7.2. Default значения

**ВАЖНО (актуализация 2026-05-28, sync с AE3 runtime):**

В **runtime AE3 (`ae3lite/`) defaults НЕ применяются**. Канон fail-closed:
- `target_ph/min/max` и `target_ec/min/max` берутся **только** из active recipe phase (`grow_cycle_phases` / `recipe_revision_phases`);
- если поле отсутствует, `runtime_plan_builder._resolve_phase_target` / `_collect_missing_paths` raise'ят `PlannerConfigurationError`, и task завершается с `error_code='ZONE_RECIPE_PHASE_TARGETS_MISSING_CRITICAL'`;
- `cycle.phase_overrides`, `cycle.manual_overrides` и `zone.logic_profile` **не могут** переопределять canonical pH/EC setpoints (см. §1 канон pH/EC targets);
- hardcoded default targets в AE3 запрещены (см. `ae3lite.md` §5.3.4).

Дефолты ниже остаются как **diagnostics/integration baseline** (legacy effective-targets API `POST /api/internal/effective-targets/batch` / `GET .../{zone_id}`) и используются Laravel при отсутствии активного цикла или для UI-подсказок. Status: **Reference defaults — used by Laravel diagnostic API only, NOT by AE3 runtime.**

Если targets не заданы в recipe, integration API возвращает следующие baseline-значения (для AE3 runtime отсутствие target всё равно даёт fail-closed):

```json
{
  "ph": {"target": 6.0, "min": 5.5, "max": 6.5},
  "ec": {"target": 1.4, "min": 1.2, "max": 1.6},
  "irrigation": {"mode": "MANUAL"},
  "lighting": {"mode": "MANUAL", "brightness": 100, "brightness_night": 0},
  "climate": {
    "temp_air": {"target": 23.0, "min": 20.0, "max": 28.0},
    "humidity_air": {"target": 60.0, "min": 50.0, "max": 70.0}
  },
  "correction_timings": {
    "tank_fill_stabilization_sec": 90,
    "tank_recirc_stabilization_sec": 30,
    "irrigation_stabilization_sec": 30,
    "irrig_recirc_stabilization_sec": 30,
    "npk_mix_time_sec": 120,
    "ph_mix_time_sec": 60,
    "ca_mg_mix_time_sec": 90,
    "min_correction_interval_sec": 300,
    "max_tank_recirc_attempts": 5,
    "max_irrig_recirc_attempts": 2,
    "tank_fill_timeout_sec": 1800,
    "tank_recirc_timeout_sec": 3600,
    "irrigation_timeout_sec": 600
  }
}
```

---

## 9. Water-baseline EC targets + sequential nutrient (канон)

**Дата:** 2026-07-22. **Статус:** канон (заменяет NPK-prepare share owner).

Legacy `target_ec_prepare` / `npk_ec_share` / «prepare = только NPK» — **deprecated**:
больше не source of truth для prepare EC. Старый текст §9 (2026-04-13) описывал
промежуточную модель и не должен использоваться при реализации pipeline.

### 9.1. Проблема (историческая) и новый контракт

Старая модель дозировала в prepare только NPK-долю полного EC (`target_ec * npk_ec_share`),
а Ca/Mg/Micro оставляла на irrigation/`irrig_recirc`. Это давало передозировку NPK и
ломало компонентную сборку при уже достигнутом full EC.

**Новый канон:**
- `solution_fill` — только **calcium** после water-baseline;
- `prepare_recirculation` — последовательный pipeline
  `Ca → pH → Mg → pH → NPK → pH → Micro → финальный pH`;
- `irrigation` — **только pH**; EC / post-irrigation nutrient recovery **запрещены**.

### 9.2. Модель таргетов (water baseline)

```
nutrient_budget = target_ec − water_ec
T_ca          = water_ec + budget * r_ca
T_ca_mg       = water_ec + budget * (r_ca + r_mg)
T_ca_mg_npk   = water_ec + budget * (r_ca + r_mg + r_npk)
T_full        = water_ec + budget   (= target_ec)
```

Где `r_*` — нормализованные `ec_component_ratios` из recipe phase
(`nutrient_*_ratio_pct` → `RecipeNutritionRuntimeConfigResolver` →
`phases.{phase}.ec_component_ratios`).

| Поле runtime / baseline | Назначение |
|-------------------------|------------|
| `water_ec`, `water_ph` | Замер чистой воды при старте `solution_fill` |
| `nutrient_budget` / `nutrient_ec_budget` | `target_ec − water_ec` |
| `component_targets` (`T_*`) | Кумулятивные EC-цели по шагам pipeline |
| `target_ec` | Полный recipe EC (и `T_full`) |
| `target_ph` | Recipe pH (все pH-gate шаги) |

Persist: таблица `zone_prepare_baselines` + колонки `ae_tasks.corr_water_*` /
`corr_nutrient_budget` / `corr_component_targets_json` (см. `DATA_MODEL_REFERENCE.md`).

**Fail-closed:**
- missing/stale baseline;
- `water_ec >= target_ec` (budget ≤ 0);
- missing ratio / actuator / `ec_component_gains` для активного компонента.

### 9.3. Выбор target по фазе / pipeline step

| Контекст | Active EC target | pH |
|----------|------------------|----|
| `solution_fill` | `T_ca` | **нет** (pH doses запрещены) |
| recirc step Ca | `T_ca` | — |
| recirc step Mg | `T_ca_mg` | — |
| recirc step NPK | `T_ca_mg_npk` | — |
| recirc step Micro | `T_full` | — |
| recirc pH-gate / final pH | EC PID frozen | `target_ph` |
| `irrigation` | EC off (`needs_ec=false`) | `target_ph` |

`build_dose_plan` / `is_within_tolerance` / `_targets_reached` используют
**active pipeline step target** (`T_step`), не legacy `target_ec_prepare`.

Legacy accessors `_effective_ec_target` с веткой `npk_ec_share` подлежат замене/
удалению в runtime PR (этот документ — канон семантики).

### 9.4. Day/night и baseline

Если `day_night_enabled=true` и активно night-окно, `target_ec` ← `day_night.ec.night`,
затем:

```
nutrient_budget = target_ec_night − water_ec
T_* = water_ec + budget * cumulative_ratios
```

Масштабирование через `npk_ec_share` (**не применяется**). Water baseline
(`water_ec`/`water_ph`) не переснимается при day/night flip внутри того же prepare —
пересчитываются только budget и `T_*`.

### 9.5. Legacy поля (compat / migration)

| Поле | Статус |
|------|--------|
| `target_ec_prepare`, `target_ec_prepare_min/max` | deprecated — не owner prepare EC |
| `npk_ec_share` | deprecated — не owner prepare EC |
| `_compute_prepare_ec_share` / `_day_night_override_scaled` (NPK share) | удалить/заменить на baseline math |
| irrigation `ec_excluded_components=["npk"]` + Ca/Mg/Micro dosing | removed — irrigation = pH-only |

---

## 10. Day/Night Override для pH/EC/климата

**Дата:** 2026-04-13.

### 10.1. Активация

Override активируется флагом фазы `day_night_enabled=true` (поле `recipe_revision_phases.day_night_enabled` / `grow_cycle_phases.day_night_enabled`, см. `RECIPE_ENGINE_FULL.md` §2.1.1).

### 10.2. Структура `extensions.day_night`

```jsonc
{
  "day_night": {
    "lighting": {
      "day_start_time": "06:00",     // HH:MM начало дневного окна (локальное время)
      "day_hours": 18                 // длительность дневного окна в часах
    },
    "ph": {
      "day": 6.0, "day_min": 5.8, "day_max": 6.2,
      "night": 6.2, "night_min": 6.0, "night_max": 6.4
    },
    "ec": {
      "day": 1.5, "day_min": 1.3, "day_max": 1.7,
      "night": 1.2, "night_min": 1.0, "night_max": 1.4
    },
    "temperature":  {"day": 24.0, "night": 18.0},
    "humidity":     {"day": 60.0, "night": 70.0},
    "soil_moisture":{"day": 60.0, "night": 50.0}
  }
}
```

Backend-валидация (pH/EC) — `App\Support\Recipes\RecipePhaseTargetValidator::validateDayNightExtensions` (`backend/laravel/app/Support/Recipes/RecipePhaseTargetValidator.php:96`):
- pH ∈ `[0..14]`, EC ∈ `[0..20]`;
- `min ≤ target ≤ max` для каждого профиля (day, night);
- ошибки добавляются на ключи `extensions.day_night.{ph|ec}.{profile}{_min|_max}`.

### 10.3. Runtime spec

Two-tank runtime spec собирает поля:

- `runtime["day_night_enabled"]` — bool;
- `runtime["day_night_config"]` — структура `{enabled, lighting, ph, ec}`, готовая к late-binding в handler (`runtime_plan_builder.py`, `_build_day_night_config`).

### 10.4. Late-binding в handler

`backend/services/automation-engine/ae3lite/application/handlers/base.py`:
- `_is_day_now(day_night_config)` — статический метод, использует `datetime.now()` (локальное время процесса AE3) и значения `day_start_time + day_hours`. При невалидных параметрах возвращает `True` (fallback на day-таргеты).
- `_day_night_override(runtime, metric, kind, default)` — выбирает `day`/`night` ключи по результату `_is_day_now`.
- `_effective_ph_target/min/max` и `_effective_ec_target/min/max` оборачивают базовое значение через override.

### 10.5. Night override + water baseline

Для prepare с активным night-override: `target_ec` ← night, затем
`nutrient_budget = target_ec_night − water_ec` и пересчёт кумулятивных `T_*`.
Legacy `_day_night_override_scaled` через `npk_ec_share` — **не применять**
(см. §9.4).

---

## 11. Compile bundle при смене фазы

При `advancePhase`, `setPhase`, `changeRecipeRevision` (любой режим) `App\Services\GrowCycleService` обязан вызвать `AutomationConfigCompiler::compileAffectedScopes(SCOPE_GROW_CYCLE, $cycleId)` после обновления `current_phase_id` / `recipe_revision_id` (`backend/laravel/app/Services/GrowCycleService.php:1188,1264,1409`). Без этого AE3 продолжит читать старый `automation_effective_bundles` snapshot и ошибочно применит targets предыдущей фазы.

Для защиты от race condition при параллельных API вызовах все три метода открываются с `GrowCycle::lockForUpdate()->firstOrFail()` (`GrowCycleService.php:1173,1250,1333`).

---

## 12. Связанные документы

- `RECIPE_ENGINE_FULL.md` — engine рецептов и фаз
- `ZONE_CONTROLLER_FULL.md` — контроллеры зон
- `CORRECTION_CYCLE_SPEC.md` — спецификация correction cycle state machine
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и системные команды
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `../04_BACKEND_CORE/REST_API_REFERENCE.md` — REST API endpoints
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — модель данных
- `ARCHITECTURE_FLOWS.md` — диаграммы архитектурных потоков
