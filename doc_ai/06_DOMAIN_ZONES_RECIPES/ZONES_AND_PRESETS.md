# ZONES_AND_PRESETS.md
# Полная архитектура зон, пресетов и рецептов в системе 2.0
# Zone Profiles • Presets • Growth Programs • Multi‑Controller Integration

Документ описывает полную модель зон (Zones), пресетов, рецептов и фаз роста в архитектуре 2.0.
Это единое ядро логики управления гидропонными теплицами.

---

# 1. Основные сущности

В 2.0 зоны описываются тремя уровнями:

```
ZONE → PRESET → RECIPE → PHASES → TARGETS → CONTROLLERS
```

Компоненты:

- **Zone Profile** – аппаратная модель зоны.
- **Preset** – преднастройки под растение/тип культуры.
- **Recipe** – программа выращивания.
- **Phases** – фазы роста.
- **Targets** – целевые значения pH/EC/климата/полива/света.
- **Controllers** – pH, EC, climate, light, irrigation.

---

# 2. Zone Profile (структура зоны)

Зона имеет:

```
id
name
hardware_profile
plant_type
active_preset
active_recipe
controllers[]
nodes[]
channels[]
capabilities
```

### 2.1. Hardware Profile

Описание оборудования зоны:

```
water_tank_volume
sensors: pH, EC, TEMPERATURE, HUM, PAR
actuators: pumps, valves, fans, heater, light
```

### 2.2. Capabilities

Отображает, что можно управлять:

- `can_ph_control`
- `can_ec_control`
- `can_climate_control`
- `can_light_control`
- `can_irrigation_control`
- `supports_energy_optimization`
- `supports_simulation`
- `supports_ai_autonomy`

---

# 3. Preset (преднастройки)

Preset определяет базовые параметры культуры:

```
id
name
plant_type
ph_optimal_range
ec_range
vpd_range
light_intensity_range
climate_ranges
irrigation_behavior
growth_profile (fast/mid/slow)
default_recipe_id
```

### Примеры пресетов:

- Листовые культуры (салат, руккола)
- Томат/огурец
- Микрозелень
- Базилик/зелень
- Клубника
- Аэропоника/ДВГ пресеты

---

# 4. Recipes (рецепты выращивания)

Рецепт — это набор фаз роста:

```
recipe_id
name
description
phases[]
created_by
ai_generated
```

### Важные особенности:

- Рецепты могут быть созданы AI.
- Рецепты могут быть симулированы (Twin & Simulation Engine).
- Рецепты могут автоматически корректироваться AI.

---

# 5. Growth Phases (фазы роста)

Каждая фаза имеет:

```
phase_index
name
duration_hours
targets: {pH, EC, temp, humidity, vpd, light, irrigation}
ai_dynamic = true/false
irrigation_strategy
notes
```

### Пример фаз:

1. **Germination Phase** 
2. **Seedling Phase** 
3. **Veg Growth Phase** 
4. **Bloom Phase** 
5. **Finishing Phase**

---

# 6. Targets (цели контроллеров)

Каждый контроллер получает целевые значения из фазы рецепта.

### 6.1 pH Targets

```
target_ph = 5.7
tolerance = ±0.1
```

### 6.2 EC Targets

```
target_ec = 1.2
min = 1.1
max = 1.4
```

### 6.3 Climate Targets

```
temp_day = 24
temp_night = 20
humidity_day = 60
humidity_night = 70
vpd = 0.8–1.2
```

### 6.4 Light Targets

```
ppfd = 200–600 μmol/m2/s
photoperiod = 16h
spectrum = preset-specific
```

### 6.5 Irrigation Targets

```
interval = 2h
duration = 8s
adaptive = true (AI-driven)
```

---

# 7. Controllers (управляющие модули)

Каждая зона включает:

- **PH Controller**
- **EC Controller**
- **Climate Controller**
- **Light Controller**
- **Irrigation Controller**
- **Energy Controller** (2.0)
- **Safety Controller**
- **AI Controller** (опционально)

Каждый контроллер получает:

```
targets → telemetry → commands → validation → dispatch → node
```

---

# 8. Zone Runtime State

В PostgreSQL хранится:

```
zone_id
current_phase
hours_in_phase
phase_progress %
recipe_progress %
next_irrigation_ts
last_irrigation_ts
controller_states
alerts
health_score
```

### 8.1. Health Score

```
0–100
```

Состоит из:

- pH stability
- EC stability
- climate stability
- irrigation adequacy
- energy efficiency
- node uptime
- alert severity

---

# 9. Preset → Recipe Auto‑Selection

Зона может автоматически выбрать рецепт:

```
if preset.default_recipe_id != null:
 set active_recipe
```

AI может предложить альтернативы.

---

# 10. AI‑Driven Dynamic Targets (2.0)

AI может корректировать цели в реальном времени:

```
ph_target_new = f(current_ph, drift, plant_stage, absorption_rate)
ec_target_new = f(evaporation, consumption, phase)
light_ppfd_new = f(outdoor_light, energy_price)
irrigation_interval_new = f(evap_rate, temp, vpd)
```

Ограничения:

- не более ±15% от рецепта
- climate safety учитывается
- digital twin проверяет безопасность

---

# 11. Zone Lifecycle

### 11.1. Create Zone

- Выбор пресета
- Выбор рецепта
- Инициализация контроллеров

### 11.2. Run

- Controllers Active
- AI Active (если включён)
- Simulation Available

### 11.3. Phase End

Фаза заканчивается:

```
current_phase += 1
reset phase hours
update targets
```

### 11.4. Recipe End

Зона попадает в:

- HOLD mode
- Harvest mode
- Auto-clean (опционально)
- Reset mode

---

# 12. Zone Safety Layer

Зона блокирует:

- полив при low water
- дозирование при no flow
- EC/pH контроль при некорректных сенсорах
- климат-контроль при неисправностях

---

# 13. Zone Alerts

Типы:

- PH_HIGH / PH_LOW
- EC_HIGH / EC_LOW
- TEMPERATURE_HIGH / TEMPERATURE_LOW
- HUM_HIGH / HUM_LOW
- LEVEL_LOW
- NO_FLOW
- NODE_DOWN
- CONTROLLER_ERROR
- ZONE_UNSTABLE
- RECIPE_MISMATCH
- PHASE_DRIFT
- AI_RESTRICTED

---

# 14. Zone Simulation (2.0)

Возможности:

- simulate phase
- simulate full recipe
- stress-testing
- safety-preview
- twin integration

---

# 15. UI Representation

UI показывает:

- текущую фазу
- цели и фактические значения
- графики pH/EC/климата
- поливы
- энергию
- фазовый прогресс
- симуляции
- AI-рекомендации

---

# 16. Правила для ИИ

ИИ может:

- создавать пресеты,
- создавать рецепты,
- корректировать фазы,
- улучшать цели.

ИИ не может:

- нарушать safety,
- выходить за пределы f(t) моделей Twin,
- изменять hardware profile,
- отключать контроллеры.

---

# 17. Чек-лист зон 2.0

1. Preset выбран корректно? 
2. Recipe и фазы настроены? 
3. Targets передаются контроллерам? 
4. AI режим активен? 
5. Simulation работает? 
6. Alerts корректны? 
7. Safety активен? 
8. UI показывает все данные? 

---

# Конец файла ZONES_AND_PRESETS.md
