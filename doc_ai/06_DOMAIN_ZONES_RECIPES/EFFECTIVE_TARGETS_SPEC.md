# EFFECTIVE_TARGETS_SPEC.md
# Спецификация Effective Targets для контроллеров зон

Документ описывает формальную спецификацию **effective-targets** — структурированных целевых значений и параметров управления для зон выращивания.

**Связанные документы:**
- `RECIPE_ENGINE_FULL.md` — engine рецептов и фаз
- `ZONE_CONTROLLER_FULL.md` — контроллеры зон
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — модель данных

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Назначение Effective Targets

**Effective targets** — это **единый источник истины** для контроллеров зон, который определяет:
- Текущие целевые значения (pH, EC, температура и т.д.)
- Допустимые диапазоны отклонений
- Режимы работы систем (полив, освещение, климат)
- Расписания и параметры автоматизации

**Принцип работы:**
1. Laravel вычисляет effective targets на основе:
   - Активного grow cycle зоны
   - Текущей фазы цикла (VEG, FLOWER и т.д.)
   - Revision рецепта
   - Базовых параметров зоны

2. Python сервисы (automation-engine, scheduler) получают targets через REST API
3. Контроллеры используют targets для принятия решений о командах

---

## 2. Источник effective targets

### 2.1. Laravel API Endpoint

**Endpoint:** `POST /api/internal/effective-targets/batch`

**Метод:** Batch получение targets для нескольких зон за один запрос.

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
        "brightness": 80
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

### 2.2. Endpoint для одной зоны

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

  // Опциональные параметры PID контроллера
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

### 4.3. Irrigation Controller

```typescript
interface IrrigationTarget {
  mode: "SCHEDULE" | "SUBSTRATE" | "FLOOD_DRAIN" | "DWC" | "MANUAL";

  // Для режима SCHEDULE
  interval_sec?: number;      // Интервал между поливами (сек)
  duration_sec?: number;      // Длительность полива (сек)
  volume_ml?: number;         // Объем полива (мл)

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

  // Для режима SCHEDULE
  on_time?: string;           // Время включения (HH:MM, например "06:00")
  off_time?: string;          // Время выключения (HH:MM, например "22:00")
  brightness?: number;        // Яркость 0-100%

  // Для режима PHOTOPERIOD
  photoperiod_hours?: number; // Длительность светового дня (часы)
  sunrise_time?: string;      // Время "восхода" (HH:MM)

  // Дополнительные параметры
  dimming?: {
    enabled: boolean;
    sunrise_duration_min: number;  // Длительность плавного включения (мин)
    sunset_duration_min: number;   // Длительность плавного выключения (мин)
  };
}
```

**Пример:**
```json
{
  "lighting": {
    "mode": "SCHEDULE",
    "on_time": "06:00",
    "off_time": "22:00",
    "brightness": 80,
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
| **TANK_FILLING** | `tank_fill_stabilization_sec` (90s) | NPK + pH |
| **TANK_RECIRC** | `tank_recirc_stabilization_sec` (30s) | NPK + pH (с `npk_mix_time_sec`, `ph_mix_time_sec`) |
| **READY** | — | Нет коррекций |
| **IRRIGATING** | `irrigation_stabilization_sec` (30s) | Ca/Mg/micro + pH |
| **IRRIG_RECIRC** | `irrig_recirc_stabilization_sec` (30s) | Ca/Mg/micro + pH (с `ca_mg_mix_time_sec`, `ph_mix_time_sec`) |

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
- `ARCHITECTURE_FLOWS.md` (секция 3.3) — диаграммы потоков коррекций

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

### 5.2. Scheduler использует targets

```python
# Получить targets для зоны
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
// Vue композабл для получения targets
export function useZoneTargets(zoneId: Ref<number>) {
  const targets = ref<EffectiveTargets | null>(null);

  async function fetchTargets() {
    const response = await axios.get(`/api/internal/effective-targets/${zoneId.value}`);
    targets.value = response.data;
  }

  return { targets, fetchTargets };
}

// Использование в компоненте
const { targets } = useZoneTargets(zoneId);

// Отображение pH targets
<div v-if="targets?.targets?.ph">
  <span>pH Target: {{ targets.targets.ph.target }}</span>
  <span>Range: {{ targets.targets.ph.min }} - {{ targets.targets.ph.max }}</span>
</div>
```

---

## 6. Вычисление effective targets

### 6.1. Источники данных

Laravel вычисляет effective targets на основе:

1. **GrowCycle** — активный цикл выращивания зоны
2. **RecipeRevision** — текущая ревизия рецепта
3. **Phase columns** — данные фазы в JSON столбцах ревизии
4. **Zone базовые параметры** — default значения зоны

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
   - Для `lighting` — `on_time` < `off_time`
   - Для `controller.ratio_a_b` — не равно 0

### 7.2. Default значения

Если targets не заданы в recipe, используются default значения:

```json
{
  "ph": {"target": 6.0, "min": 5.5, "max": 6.5},
  "ec": {"target": 1.4, "min": 1.2, "max": 1.6},
  "irrigation": {"mode": "MANUAL"},
  "lighting": {"mode": "MANUAL", "brightness": 100},
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

## 8. Связанные документы

- `RECIPE_ENGINE_FULL.md` — engine рецептов и фаз
- `ZONE_CONTROLLER_FULL.md` — контроллеры зон
- `CORRECTION_CYCLE_SPEC.md` — спецификация correction cycle state machine
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и системные команды
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `../04_BACKEND_CORE/REST_API_REFERENCE.md` — REST API endpoints
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — модель данных
- `ARCHITECTURE_FLOWS.md` — диаграммы архитектурных потоков
