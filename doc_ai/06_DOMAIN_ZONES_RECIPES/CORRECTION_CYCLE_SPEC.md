# CORRECTION_CYCLE_SPEC.md
# Спецификация циклов коррекции раствора

Документ описывает state machine, режимы коррекции и логику управления измерением pH/EC с учетом необходимости наличия потока раствора.

**Дата создания:** 2026-02-14
**Статус:** Рабочий документ (требует валидации)

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Проблема и решение

### 1.1. Проблема

**Измерения pH и EC достоверны только при наличии потока раствора через датчики.**

Без потока:
- Датчики измеряют стоячий раствор
- Показания могут быть неточными
- Стратификация раствора в баке
- Коррекция на основе таких данных приводит к ошибкам

### 1.2. Решение

**Ноды pH и EC работают в двух режимах:**

1. **IDLE (ожидание)** — без активации
   - Отправляют только heartbeat и LWT
   - НЕ отправляют telemetry сенсоров
   - НЕ принимают команды коррекции

2. **ACTIVE (активный)** — после активации
   - Сразу начинают отправлять telemetry
   - После стабилизации разрешают коррекцию
   - Automation-engine управляет активацией

**Активация нод происходит когда:**
- Включается поток раствора (pump_in или circulation_pump)
- Начинается режим коррекции

**Деактивация нод происходит когда:**
- Поток останавливается
- Режим коррекции завершен

---

## 2. State Machine зоны коррекции

### 2.1. Состояния (Zone Correction States)

```
┌──────────────┐
│   IDLE       │  ◄─── Начальное состояние
│              │       Нет потока, датчики неактивны
└──────┬───────┘
       │ start_tank_fill
       │
       ▼
┌──────────────┐
│ TANK_FILLING │  ◄─── Набор бака с раствором
│              │       Поток активен, NPK + pH коррекция
└──────┬───────┘
       │ targets_not_achieved
       │
       ▼
┌──────────────┐
│ TANK_RECIRC  │  ◄─── Рециркуляция бака
│              │       До достижения целевых NPK + pH
└──────┬───────┘
       │ targets_achieved
       │
       ▼
┌──────────────┐
│  READY       │  ◄─── Раствор готов
│              │       Ожидание полива
└──────┬───────┘
       │ start_irrigation
       │
       ▼
┌──────────────┐
│ IRRIGATING   │  ◄─── Полив зоны
│              │       Ca/Mg/микро + pH коррекция
└──────┬───────┘
       │ targets_not_achieved OR need_correction
       │
       ▼
┌──────────────┐
│ IRRIG_RECIRC │  ◄─── Рециркуляция при поливе
│              │       До достижения Ca/Mg/микро + pH
└──────┬───────┘
       │ targets_achieved OR irrigation_complete
       │
       ▼
     IDLE или READY
```

### 2.2. Описание состояний

| Состояние | Поток | pH/EC активны | Коррекция | Типы корр-и |
|-----------|-------|---------------|-----------|-------------|
| **IDLE** | ❌ Нет | ❌ Нет | ❌ Нет | - |
| **TANK_FILLING** | ✅ Да | ✅ Да | ✅ Да | NPK, pH |
| **TANK_RECIRC** | ✅ Да | ✅ Да | ✅ Да | NPK, pH |
| **READY** | ❌ Нет | ❌ Нет | ❌ Нет | - |
| **IRRIGATING** | ✅ Да | ✅ Да | ✅ Да | Ca/Mg/микро, pH |
| **IRRIG_RECIRC** | ✅ Да | ✅ Да | ✅ Да | Ca/Mg/микро, pH |

### 2.3. События (Triggers)

| Событие | Описание | Откуда |
|---------|----------|--------|
| `start_tank_fill` | Начать набор бака | Scheduler / Manual |
| `start_irrigation` | Начать полив | Scheduler / Manual |
| `targets_achieved` | Целевые значения достигнуты | Automation-engine |
| `targets_not_achieved` | Целевые значения НЕ достигнуты | Automation-engine |
| `need_correction` | Нужна коррекция во время полива | Automation-engine |
| `irrigation_complete` | Полив завершен | Pump node |
| `timeout` | Таймаут режима | Automation-engine |
| `error` | Ошибка (нет данных, нет нод) | Automation-engine |

---

## 3. Режимы коррекции

### 3.1. Режим 1: TANK_FILLING (Набор бака)

**Цель:** Набрать бак с раствором и скорректировать NPK + pH до целевых значений.

**Последовательность:**
```
1. Automation-engine → MQTT: activate ph_node, ec_node
2. Automation-engine → MQTT: start pump_in (набор бака)
3. Ожидание стабилизации (60-120 сек, настраиваемо)
4. pH/EC ноды → MQTT: telemetry с flow_active: true, stable: false
5. После стабилизации: stable: true
6. Automation-engine: проверка EC (NPK)
   - Если EC < target: дозирование NPK (компоненты A+B)
   - Ожидание смешивания (120 сек)
   - Повторное измерение
7. Automation-engine: проверка pH
   - Если pH вне диапазона: дозирование pH+/pH-
   - Ожидание смешивания (60 сек)
   - Повторное измерение
8. Если targets достигнуты:
   - → Состояние READY
   - Automation-engine → MQTT: stop pump_in
   - Automation-engine → MQTT: deactivate ph_node, ec_node
9. Если targets НЕ достигнуты:
   - → Состояние TANK_RECIRC
```

**Коррекция:**
- NPK (EC): Компоненты A + B в соотношении из effective-targets
- pH: pH+ или pH- в зависимости от отклонения

### 3.2. Режим 2: TANK_RECIRC (Рециркуляция бака)

**Цель:** Циркулировать раствор до достижения целевых NPK + pH.

**Последовательность:**
```
1. pH/EC ноды уже активны (из TANK_FILLING)
2. Automation-engine → MQTT: start circulation_pump (рециркуляция)
3. Ожидание стабилизации (30 сек, короче чем при filling)
4. Повторение шагов 6-7 из TANK_FILLING
5. Если targets достигнуты после N попыток (max 5):
   - → Состояние READY
   - Automation-engine → MQTT: stop circulation_pump
   - Automation-engine → MQTT: deactivate ph_node, ec_node
6. Если targets НЕ достигнуты после 5 попыток:
   - → Состояние IDLE (с ошибкой)
   - Alert: "Failed to achieve NPK/pH targets"
```

**Макс попытки:** 5
**Интервал между попытками:** 2 мин

### 3.3. Режим 3: IRRIGATING (Полив)

**Цель:** Поливать зону и корректировать Ca/Mg/микро + pH по необходимости.

**Последовательность:**
```
1. Automation-engine → MQTT: activate ph_node, ec_node
2. Automation-engine → MQTT: start pump_in (полив)
3. Ожидание стабилизации (30 сек, быстрая)
4. pH/EC ноды → MQTT: telemetry с flow_active: true
5. Automation-engine: проверка pH во время полива
   - Если pH вне диапазона: дозирование pH+/pH-
   - Минимальный интервал между дозами: 5 мин
6. Automation-engine: проверка Ca/Mg/микро (optional)
   - Если EC ниже нормы: дозирование Ca/Mg
7. Полив продолжается до завершения (по volume_ml или duration_sec)
8. После завершения полива:
   - Если pH/EC в норме:
     - → Состояние IDLE
     - Automation-engine → MQTT: deactivate ph_node, ec_node
   - Если pH/EC вне нормы:
     - → Состояние IRRIG_RECIRC
```

**Коррекция:**
- Ca/Mg/микро: При необходимости (опционально)
- pH: При отклонении во время полива (приоритет)

### 3.4. Режим 4: IRRIG_RECIRC (Рециркуляция при поливе)

**Цель:** Быстро скорректировать pH и Ca/Mg после полива.

**Последовательность:**
```
1. pH/EC ноды уже активны (из IRRIGATING)
2. Automation-engine → MQTT: stop pump_in
3. Automation-engine → MQTT: start circulation_pump
4. Ожидание стабилизации (30 сек)
5. Коррекция pH (приоритет) и Ca/Mg если нужно
6. Максимум 2 попытки
7. После достижения targets или timeout:
   - → Состояние IDLE
   - Automation-engine → MQTT: stop circulation_pump
   - Automation-engine → MQTT: deactivate ph_node, ec_node
```

**Макс попытки:** 2
**Интервал:** 1 мин

---

## 4. Команды активации/деактивации нод

### 4.1. Команда ACTIVATE (для ph_node, ec_node)

**Topic:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "activate_sensor_mode",
  "params": {
    "stabilization_time_sec": 60  // Время до stable: true
  },
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3..."
}
```

**Действия ноды после получения:**
1. Переход в режим ACTIVE
2. Начать отправку telemetry каждые 5 сек
3. В первых сообщениях: `stable: false`
4. Через `stabilization_time_sec`: `stable: true`
5. Разрешить команды дозирования (если есть)

**Telemetry во время активации:**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001234,
  "flow_active": true,    // ← поток активен
  "stable": false,        // ← еще не стабилизировалось
  "stabilization_progress_sec": 15  // ← прогресс стабилизации
}
```

После стабилизации:
```json
{
  "metric_type": "PH",
  "value": 5.92,
  "ts": 1710001294,
  "flow_active": true,
  "stable": true,         // ← стабилизировалось!
  "corrections_allowed": true  // ← можно дозировать
}
```

### 4.2. Команда DEACTIVATE

**Topic:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "deactivate_sensor_mode",
  "params": {},
  "cmd_id": "cmd-deactivate-456",
  "ts": 1710002000,
  "sig": "b2c3d4..."
}
```

**Действия ноды после получения:**
1. Переход в режим IDLE
2. Прекратить отправку telemetry сенсоров
3. Отправлять только heartbeat и LWT
4. Игнорировать команды дозирования (если будут)

### 4.3. Новый topic для system команд

Для команд управления режимом (не относятся к каналам):

**Format:** `hydro/{gh}/{zone}/{node}/system/command`

**Примеры:**
- `hydro/gh-1/zn-1/nd-ph-1/system/command`
- `hydro/gh-1/zn-1/nd-ec-1/system/command`

---

## 5. Временные параметры (настраиваемые через effective-targets)

### 5.1. Параметры стабилизации

```typescript
interface CorrectionTimings {
  // Время стабилизации после активации
  tank_fill_stabilization_sec: number;     // По умолчанию: 90
  tank_recirc_stabilization_sec: number;   // По умолчанию: 30
  irrigation_stabilization_sec: number;    // По умолчанию: 30
  irrig_recirc_stabilization_sec: number;  // По умолчанию: 30

  // Время ожидания после дозирования
  npk_mix_time_sec: number;                // По умолчанию: 120
  ph_mix_time_sec: number;                 // По умолчанию: 60
  ca_mg_mix_time_sec: number;              // По умолчанию: 90

  // Интервалы коррекции
  min_correction_interval_sec: number;     // По умолчанию: 300 (5 мин)

  // Макс попытки
  max_tank_recirc_attempts: number;        // По умолчанию: 5
  max_irrig_recirc_attempts: number;       // По умолчанию: 2

  // Timeout режимов
  tank_fill_timeout_sec: number;           // По умолчанию: 1800 (30 мин)
  tank_recirc_timeout_sec: number;         // По умолчанию: 3600 (1 час)
  irrigation_timeout_sec: number;          // По умолчанию: 600 (10 мин)
}
```

### 5.2. Добавление в effective-targets

Эти параметры добавляются в `effective-targets` для зоны:

```json
{
  "cycle_id": 123,
  "targets": {
    "ph": {...},
    "ec": {...},
    "correction_timings": {
      "tank_fill_stabilization_sec": 90,
      "tank_recirc_stabilization_sec": 30,
      "irrigation_stabilization_sec": 30,
      "npk_mix_time_sec": 120,
      "ph_mix_time_sec": 60,
      "min_correction_interval_sec": 300,
      "max_tank_recirc_attempts": 5,
      "max_irrig_recirc_attempts": 2
    }
  }
}
```

---

## 6. Логика automation-engine

### 6.1. Новый компонент: CorrectionStateMachine

```python
class CorrectionStateMachine:
    """
    State machine для управления циклами коррекции зоны.
    """

    def __init__(self, zone_id: int):
        self.zone_id = zone_id
        self.state: CorrectionState = CorrectionState.IDLE
        self.attempt_count = 0
        self.last_correction_ts = None
        self.ph_ec_nodes_active = False

    async def transition(self, event: CorrectionEvent):
        """Обработка события и переход в новое состояние."""
        new_state = self._get_next_state(self.state, event)
        await self._on_exit_state(self.state)
        self.state = new_state
        await self._on_enter_state(new_state)

    async def _on_enter_state(self, state: CorrectionState):
        """Действия при входе в состояние."""
        if state == CorrectionState.TANK_FILLING:
            await self._activate_ph_ec_nodes()
            await self._start_pump("pump_in")
            await self._wait_stabilization("tank_fill")

        elif state == CorrectionState.TANK_RECIRC:
            await self._start_pump("circulation_pump")
            await self._wait_stabilization("tank_recirc")
            self.attempt_count = 0

        elif state == CorrectionState.READY:
            await self._deactivate_ph_ec_nodes()
            await self._stop_all_pumps()

        elif state == CorrectionState.IRRIGATING:
            await self._activate_ph_ec_nodes()
            await self._start_pump("pump_in")
            await self._wait_stabilization("irrigation")

        elif state == CorrectionState.IRRIG_RECIRC:
            await self._stop_pump("pump_in")
            await self._start_pump("circulation_pump")
            await self._wait_stabilization("irrig_recirc")
            self.attempt_count = 0

        elif state == CorrectionState.IDLE:
            await self._deactivate_ph_ec_nodes()
            await self._stop_all_pumps()

    async def _activate_ph_ec_nodes(self):
        """Активация pH и EC нод."""
        timings = await self._get_correction_timings()

        # Активировать pH ноду
        await send_command(
            node_uid="nd-ph-1",
            topic_suffix="system/command",
            cmd="activate_sensor_mode",
            params={
                "stabilization_time_sec": timings.get("tank_fill_stabilization_sec", 90)
            }
        )

        # Активировать EC ноду
        await send_command(
            node_uid="nd-ec-1",
            topic_suffix="system/command",
            cmd="activate_sensor_mode",
            params={
                "stabilization_time_sec": timings.get("tank_fill_stabilization_sec", 90)
            }
        )

        self.ph_ec_nodes_active = True

    async def _deactivate_ph_ec_nodes(self):
        """Деактивация pH и EC нод."""
        await send_command(
            node_uid="nd-ph-1",
            topic_suffix="system/command",
            cmd="deactivate_sensor_mode"
        )

        await send_command(
            node_uid="nd-ec-1",
            topic_suffix="system/command",
            cmd="deactivate_sensor_mode"
        )

        self.ph_ec_nodes_active = False

    async def check_and_correct(self):
        """Проверка и коррекция pH/EC в текущем состоянии."""
        if self.state == CorrectionState.TANK_FILLING:
            await self._correct_npk_and_ph()

        elif self.state == CorrectionState.TANK_RECIRC:
            success = await self._correct_npk_and_ph()
            self.attempt_count += 1

            if success:
                await self.transition(CorrectionEvent.TARGETS_ACHIEVED)
            elif self.attempt_count >= self._get_max_attempts("tank_recirc"):
                await self.transition(CorrectionEvent.TIMEOUT)

        elif self.state == CorrectionState.IRRIGATING:
            await self._correct_ph()  # Только pH во время полива
            # Ca/Mg опционально

        elif self.state == CorrectionState.IRRIG_RECIRC:
            success = await self._correct_ph()
            self.attempt_count += 1

            if success or self.attempt_count >= self._get_max_attempts("irrig_recirc"):
                await self.transition(CorrectionEvent.IRRIGATION_COMPLETE)

    async def _correct_npk_and_ph(self) -> bool:
        """Коррекция NPK (EC) и pH."""
        # Получить текущую телеметрию
        telemetry = await get_stable_telemetry(self.zone_id)
        if not telemetry or not telemetry.stable:
            return False

        targets = await get_effective_targets(self.zone_id)
        success = True

        # Коррекция EC (NPK)
        if telemetry.ec < targets.ec.min:
            dose_a, dose_b = calculate_npk_dose(telemetry.ec, targets.ec.target)
            await dose_npk(self.zone_id, dose_a, dose_b)
            await asyncio.sleep(targets.timings.npk_mix_time_sec)
            success = False  # Нужна повторная проверка

        # Коррекция pH
        if telemetry.ph < targets.ph.min:
            dose = calculate_ph_dose(telemetry.ph, targets.ph.target)
            await dose_ph_up(self.zone_id, dose)
            await asyncio.sleep(targets.timings.ph_mix_time_sec)
            success = False

        elif telemetry.ph > targets.ph.max:
            dose = calculate_ph_dose(telemetry.ph, targets.ph.target)
            await dose_ph_down(self.zone_id, dose)
            await asyncio.sleep(targets.timings.ph_mix_time_sec)
            success = False

        return success
```

---

## 7. Изменения в прошивках нод

### 7.1. pH node / EC node

**Новые состояния:**
```c
typedef enum {
    SENSOR_MODE_IDLE,      // Только heartbeat/LWT
    SENSOR_MODE_ACTIVE,    // Telemetry + corrections
} sensor_mode_t;
```

**Новая логика:**
```c
// В main loop ноды
void sensor_node_loop() {
    if (sensor_mode == SENSOR_MODE_IDLE) {
        // Отправлять только heartbeat каждые 60 сек
        send_heartbeat();
        vTaskDelay(60000 / portTICK_PERIOD_MS);
        return;
    }

    // SENSOR_MODE_ACTIVE
    if (!stable) {
        // Еще не стабилизировалось
        stabilization_elapsed_sec += 5;
        if (stabilization_elapsed_sec >= stabilization_target_sec) {
            stable = true;
        }
    }

    // Измерить и отправить telemetry
    float ph_value = read_ph_sensor();
    send_telemetry(ph_value, stable);

    vTaskDelay(5000 / portTICK_PERIOD_MS);  // Каждые 5 сек
}

// Command handler
void handle_system_command(const char* cmd, cJSON* params) {
    if (strcmp(cmd, "activate_sensor_mode") == 0) {
        sensor_mode = SENSOR_MODE_ACTIVE;
        stable = false;
        stabilization_elapsed_sec = 0;
        stabilization_target_sec = cJSON_GetNumberValue(cJSON_GetObjectItem(params, "stabilization_time_sec"));
        ESP_LOGI(TAG, "Sensor mode activated, stabilization: %d sec", stabilization_target_sec);

    } else if (strcmp(cmd, "deactivate_sensor_mode") == 0) {
        sensor_mode = SENSOR_MODE_IDLE;
        stable = false;
        ESP_LOGI(TAG, "Sensor mode deactivated");
    }
}
```

---

## 8. Frontend настройки

### 8.1. Секция "Коррекция" в Zone Settings

```vue
<template>
  <div class="correction-settings">
    <h3>Параметры коррекции раствора</h3>

    <div class="timing-group">
      <label>Время стабилизации (набор бака)</label>
      <input v-model="timings.tank_fill_stabilization_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Время смешивания NPK</label>
      <input v-model="timings.npk_mix_time_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Время смешивания pH</label>
      <input v-model="timings.ph_mix_time_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Макс попыток рециркуляции бака</label>
      <input v-model="timings.max_tank_recirc_attempts" type="number" min="1" max="10" />
    </div>

    <button @click="saveTimings">Сохранить</button>
  </div>
</template>
```

---

## 9. Связанные документы

- `ARCHITECTURE_FLOWS.md` — архитектурные схемы и пайплайны
- `EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол
- `../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — каналы нод

---

**Документ создан после обсуждения логики коррекции 2026-02-14**
