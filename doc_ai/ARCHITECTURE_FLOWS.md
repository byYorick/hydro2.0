# ARCHITECTURE_FLOWS.md
# Архитектурные схемы и пайплайны hydro2.0

Документ содержит визуализацию архитектурных потоков данных и взаимодействия компонентов системы hydro2.0.

**Дата создания:** 2026-02-14
**Статус:** Актуальный (после аудита документации)

---

## 1. Общая архитектура системы

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HYDRO 2.0 SYSTEM                            │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐     MQTT      ┌──────────────────────────────────┐
│  ESP32 Nodes │◄──────────────►│      MQTT Broker (Mosquitto)     │
│              │   (Port 1883)  │                                  │
│ - ph_node    │                └──────────────────────────────────┘
│ - ec_node    │                         ▲          ▲
│ - pump_node  │                         │          │
│ - climate    │                    Subscribe   Publish
│ - light      │                         │          │
│ - relay      │                ┌────────┴──────────┴────────┐
└──────────────┘                │   Python Services Layer    │
                                │                             │
                         ┌──────┴─────────────────────┬──────┴──────┐
                         │                            │             │
                    ┌────▼─────┐              ┌──────▼──────┐ ┌────▼─────┐
                    │ History- │              │ Automation- │ │ Scheduler│
                    │ Logger   │              │ Engine      │ │          │
                    │ :9300/01 │              │ :9401/9405  │ │ :9402    │
                    └────┬─────┘              └──────┬──────┘ └────┬─────┘
                         │                           │             │
                         │    PostgreSQL + TimescaleDB             │
                         └───────────────┬───────────┴─────────────┘
                                        │
                                 ┌──────▼──────┐
                                 │  PostgreSQL │
                                 │  :5432      │
                                 │             │
                                 │ - zones     │
                                 │ - nodes     │
                                 │ - telemetry │
                                 │ - commands  │
                                 └──────┬──────┘
                                        │
                         ┌──────────────┴──────────────┐
                         │                             │
                    ┌────▼─────┐              ┌───────▼────────┐
                    │ Laravel  │              │ WebSocket      │
                    │ Backend  │              │ (Reverb)       │
                    │ :8080    │              │ :8080/reverb   │
                    └────┬─────┘              └───────┬────────┘
                         │                            │
                         │          HTTP/WS           │
                         └──────────┬─────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Vue 3 Frontend    │
                         │   (Inertia.js)      │
                         │                     │
                         │ - Dashboard         │
                         │ - Zone Management   │
                         │ - Node Control      │
                         └─────────────────────┘
```

---

## 2. Пайплайн телеметрии (ESP32 → Backend → Frontend)

### 2.1. Поток telemetry данных

```
┌──────────────┐
│  ESP32 Node  │
│  (ph_node)   │
└──────┬───────┘
       │ 1. Измерение pH сенсора
       │    value = 5.86
       │
       │ 2. Формирование MQTT сообщения
       │
       ▼
Topic: hydro/gh-1/zn-3/nd-ph-1/ph_main/telemetry
Payload:
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001234
}
       │
       │ 3. Публикация в MQTT (QoS=1)
       │
       ▼
┌──────────────────┐
│  MQTT Broker     │
│  (Mosquitto)     │
└──────┬───────────┘
       │ 4. Broadcast подписчикам
       │
       ▼
┌──────────────────┐
│ history-logger   │ ◄─── Подписка на hydro/+/+/+/+/telemetry
│ :9300            │
└──────┬───────────┘
       │ 5. Парсинг JSON payload
       │ 6. Валидация metric_type
       │
       │ 7. Батчинг (накопление до 200 записей или 500ms)
       │
       ▼
┌──────────────────┐
│  PostgreSQL      │
│  :5432           │
├──────────────────┤
│ telemetry_samples│ ◄─── 8. Batch INSERT (upsert)
│ - id             │      INSERT INTO telemetry_samples
│ - zone_id        │      (zone_id, node_uid, channel,
│ - node_uid       │       metric_type, value, ts)
│ - channel        │      VALUES (...)
│ - metric_type    │      ON CONFLICT DO UPDATE
│ - value          │
│ - ts             │
├──────────────────┤
│ telemetry_last   │ ◄─── 9. UPDATE last value
│ - zone_id        │      UPDATE telemetry_last
│ - node_uid       │      SET value = 5.86,
│ - channel        │          last_updated_at = NOW()
│ - metric_type    │      WHERE zone_id = 3
│ - value          │        AND metric_type = 'PH'
│ - last_updated_at│
└──────┬───────────┘
       │
       │ 10. WebSocket событие (опционально)
       │
       ▼
┌──────────────────┐
│  Laravel         │
│  + Reverb        │
└──────┬───────────┘
       │ 11. Broadcast WebSocket
       │     TelemetryUpdated event
       │
       ▼
┌──────────────────┐
│  Vue 3 Frontend  │
│                  │
│  ┌────────────┐  │
│  │ Dashboard  │  │ ◄─── 12. Real-time update графика
│  │ pH Chart   │  │      chart.updateData({ph: 5.86})
│  └────────────┘  │
└──────────────────┘
```

### 2.2. Timing диаграмма telemetry

```
ESP32         MQTT          history-logger    PostgreSQL      Frontend
  │             │                  │               │              │
  ├─measure─────┤                  │               │              │
  │  (~100ms)   │                  │               │              │
  │             │                  │               │              │
  ├─publish─────►                  │               │              │
  │  (~10ms)    │                  │               │              │
  │             ├─broadcast────────►               │              │
  │             │  (~5ms)          │               │              │
  │             │                  ├─batch─────────┤              │
  │             │                  │  (500ms)      │              │
  │             │                  │               │              │
  │             │                  ├─INSERT────────►              │
  │             │                  │  (~20ms)      │              │
  │             │                  │               │              │
  │             │                  │               ├─UPDATE───────►
  │             │                  │               │  (~50ms)     │
  │             │                  │               │              │
  │             │                  │               │  Display     │
  │             │                  │               │  (~10ms)     │
  │             │                  │               │              │

Total latency: ~695ms (от измерения до отображения)
```

---

## 3. Пайплайн команд (Frontend → Backend → ESP32)

### 3.1. Поток commands (многоуровневая архитектура)

```
┌──────────────────┐
│  Vue 3 Frontend  │
│                  │
│  ┌────────────┐  │
│  │ Zone       │  │
│  │ Control    │  │ ◄─── 1. Пользователь нажимает "Полить"
│  │ Panel      │  │
│  └────────────┘  │
└──────┬───────────┘
       │ 2. HTTP POST /api/zones/1/commands
       │    {type: "FORCE_IRRIGATION", params: {duration_sec: 60}}
       │
       ▼
┌──────────────────┐
│  Laravel         │
│  :8080           │
│                  │
│  ZoneController  │ ◄─── 3. Валидация прав доступа (Sanctum)
│  ::sendCommand() │      4. Валидация параметров
└──────┬───────────┘
       │ 5. НЕ обращается к MQTT напрямую!
       │    Вместо этого -> Python сервис
       │
       │ 6. HTTP POST http://history-logger:9300/zones/1/commands
       │    {
       │      "type": "FORCE_IRRIGATION",
       │      "params": {"duration_sec": 60},
       │      "greenhouse_uid": "gh-1",
       │      "node_uid": "nd-pump-1",
       │      "channel": "pump_in"
       │    }
       │
       ▼
┌──────────────────┐
│ history-logger   │
│ :9300            │ ◄─── ЕДИНСТВЕННАЯ точка публикации в MQTT
│                  │
│ POST /commands   │ ◄─── 7. Валидация команды
└──────┬───────────┘      8. Добавление HMAC подписи
       │                  9. Логирование в БД (commands таблица)
       │
       │ 10. Формирование MQTT команды
       │
       ▼
Topic: hydro/gh-1/zn-1/nd-pump-1/pump_in/command
Payload:
{
  "cmd": "run_pump",
  "params": {"duration_ms": 60000},
  "cmd_id": "cmd-abc123",
  "ts": 1710001234,
  "sig": "a1b2c3d4e5f6..."
}
       │
       │ 11. Публикация в MQTT (QoS=1, Retain=false)
       │
       ▼
┌──────────────────┐
│  MQTT Broker     │
│  (Mosquitto)     │
└──────┬───────────┘
       │ 12. Доставка подписчику
       │
       ▼
┌──────────────────┐
│  ESP32 Node      │
│  (nd-pump-1)     │ ◄─── Подписка на hydro/gh-1/zn-1/nd-pump-1/+/command
│                  │
│ ┌──────────────┐ │
│ │ Command      │ │ ◄─── 13. Проверка HMAC подписи
│ │ Handler      │ │      14. Валидация timestamp (<10 sec)
│ └──────────────┘ │      15. Выполнение команды
│                  │
│ ┌──────────────┐ │
│ │ Pump Driver  │ │ ◄─── 16. GPIO включение насоса
│ └──────────────┘ │      17. Таймер на 60 секунд
└──────┬───────────┘
       │ 18. Отправка command_response
       │
       ▼
Topic: hydro/gh-1/zn-1/nd-pump-1/pump_in/command_response
Payload:
{
  "cmd_id": "cmd-abc123",
  "status": "DONE",
  "details": {"executed_ms": 60012}
}
       │
       │ 19. MQTT публикация
       │
       ▼
┌──────────────────┐
│ history-logger   │ ◄─── 20. Логирование response в БД
│ :9300            │
└──────────────────┘
```

### 3.2. Scheduler-Task пайплайн (автоматизация)

```
┌──────────────────┐
│  Scheduler       │
│  :9402           │
│                  │
│ ┌──────────────┐ │
│ │ Cron Loop    │ │ ◄─── 1. Проверка расписания (каждые 60 сек)
│ │ check_tasks()│ │      2. Найдена задача полива на 10:00
│ └──────────────┘ │
└──────┬───────────┘
       │ 3. Создание scheduler-task
       │    {
       │      "task_id": "task-irr-001",
       │      "type": "IRRIGATION",
       │      "zone_id": 1,
       │      "params": {"duration_sec": 60}
       │    }
       │
       │ 4. HTTP POST http://automation-engine:9405/scheduler/task
       │
       ▼
┌──────────────────┐
│ Automation-      │
│ Engine           │
│ :9405            │
│                  │
│ POST /scheduler/ │ ◄─── 5. Получение scheduler-task
│ task             │
│                  │
│ ┌──────────────┐ │
│ │ Task         │ │ ◄─── 6. Загрузка effective-targets для зоны 1
│ │ Processor    │ │      GET http://laravel/api/internal/effective-targets/1
│ └──────────────┘ │
│                  │      7. Определение ноды/канала для полива
│                  │         node_uid = "nd-pump-1"
│                  │         channel = "pump_in"
│                  │
│                  │      8. Преобразование IRRIGATION -> run_pump
└──────┬───────────┘
       │ 9. HTTP POST http://history-logger:9300/commands
       │    {
       │      "greenhouse_uid": "gh-1",
       │      "zone_id": 1,
       │      "node_uid": "nd-pump-1",
       │      "channel": "pump_in",
       │      "type": "run_pump",
       │      "params": {"duration_ms": 60000},
       │      "context": {
       │        "task_id": "task-irr-001",
       │        "source": "scheduler"
       │      }
       │    }
       │
       ▼
┌──────────────────┐
│ history-logger   │ ◄─── ЕДИНСТВЕННАЯ точка публикации
│ :9300            │
│                  │      10. HMAC подпись
│ POST /commands   │      11. MQTT публикация
└──────┬───────────┘      12. Логирование
       │
       ▼
    [ MQTT → ESP32 ] (см. раздел 3.1, шаги 11-20)
```

### 3.3. Automation-Engine пайплайн (коррекция pH/EC с state machine)

**ВАЖНО:** pH/EC измерения валидны только при потоке через сенсор. Automation-Engine управляет state machine с 6 состояниями и 4 режимами коррекций.

#### 3.3.1. State Machine (6 состояний)

```
          ┌─────────────────────────────────────────────────────┐
          │                  CORRECTION STATE MACHINE            │
          └─────────────────────────────────────────────────────┘
                                   │
                                   │ Старт цикла
                                   │
                                   ▼
                            ┌──────────┐
                            │   IDLE   │ ◄──────────────────┐
                            │          │                    │
                            │ - Нет    │                    │
                            │   потока │                    │
                            │ - Ноды   │                    │
                            │   неакт. │                    │
                            └────┬─────┘                    │
                                 │                          │
                                 │ Команда START_TANK_FILL  │
                                 │                          │
                                 ▼                          │
                      ┌──────────────────┐                  │
                      │  TANK_FILLING    │                  │
                      │                  │                  │
                      │ - Активация pH/EC│                  │
                      │ - Коррекция NPK  │                  │
                      │ - Коррекция pH   │                  │
                      └────┬─────────────┘                  │
                           │                                │
                           │ Достигнут уровень              │
                           │                                │
                           ▼                                │
                    ┌────────────────┐                      │
                    │  TANK_RECIRC   │                      │
                    │                │                      │
                    │ - Рециркуляция │                      │
                    │ - Коррекция NPK│                      │
                    │ - Коррекция pH │                      │
                    └────┬───────────┘                      │
                         │                                  │
                         │ NPK & pH в целевых               │
                         │                                  │
                         ▼                                  │
                   ┌──────────┐                             │
                   │  READY   │                             │
                   │          │                             │
                   │ - Готов  │                             │
                   │   к пол. │                             │
                   │ - Деакт. │                             │
                   │   нод    │                             │
                   └────┬─────┘                             │
                        │                                   │
                        │ Команда START_IRRIGATION          │
                        │                                   │
                        ▼                                   │
                ┌──────────────────┐                        │
                │   IRRIGATING     │                        │
                │                  │                        │
                │ - Активация pH/EC│                        │
                │ - Коррекция      │                        │
                │   Ca/Mg/micro    │                        │
                │ - Коррекция pH   │                        │
                └────┬─────────────┘                        │
                     │                                      │
                     │ Полив завершен                       │
                     │                                      │
                     ▼                                      │
              ┌────────────────┐                            │
              │  IRRIG_RECIRC  │                            │
              │                │                            │
              │ - Рециркуляция │                            │
              │ - Коррекция    │                            │
              │   Ca/Mg/micro  │                            │
              │ - Коррекция pH │                            │
              └────┬───────────┘                            │
                   │                                        │
                   │ Ca/Mg/micro & pH в целевых             │
                   │ ИЛИ команда END_CYCLE                  │
                   │                                        │
                   └────────────────────────────────────────┘
```

#### 3.3.2. Типы коррекций по режимам

| Режим | NPK (EC) | Ca/Mg/micro | pH |
|-------|----------|-------------|-----|
| **TANK_FILLING** | ✅ | ❌ | ✅ |
| **TANK_RECIRC** | ✅ | ❌ | ✅ |
| **IRRIGATING** | ❌ | ✅ | ✅ |
| **IRRIG_RECIRC** | ❌ | ✅ | ✅ |

#### 3.3.3. Полный пайплайн коррекции (пример TANK_FILLING)

```
┌──────────────────┐
│ Automation-      │
│ Engine           │
│ :9405            │
│                  │
│ ┌──────────────┐ │
│ │ Control Loop │ │ ◄─── 1. Проверка зон (каждые 10 сек)
│ │ check_zones()│ │      current_state = IDLE
│ └──────────────┘ │
└──────┬───────────┘
       │ 2. Получена команда START_TANK_FILL
       │    {zone_id: 1, target_volume_l: 100}
       │
       │ 3. Загрузка effective-targets для зоны 1
       │    GET http://laravel/api/internal/effective-targets/1
       │
       │ Response:
       │ {
       │   "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
       │   "ec": {"target": 1.8, "min": 1.6, "max": 2.0},
       │   "correction_timings": {
       │     "stabilization_time_sec": 60,
       │     "min_interval_sec": 300
       │   }
       │ }
       │
       ▼
┌──────────────────┐
│ State Machine    │
│ перевод в        │ ◄─── 4. Переход IDLE → TANK_FILLING
│ TANK_FILLING     │      5. Запомнить время перехода
└──────┬───────────┘
       │
       │ 6. Активация pH/EC нод (перед измерениями!)
       │
       ▼
┌──────────────────┐
│ history-logger   │ ◄─── 7. POST /commands (активация pH ноды)
│ :9300            │    {
│                  │      "node_uid": "nd-ph-1",
└──────┬───────────┘      "channel": "system",
       │                  "type": "activate_sensor_mode",
       │                  "params": {"stabilization_time_sec": 60}
       │                }
       │
       ▼
Topic: hydro/gh-1/zn-1/nd-ph-1/system/command
       │
       ▼
┌──────────────────┐
│  pH Node         │ ◄─── 8. Получение activate_sensor_mode
│  (nd-ph-1)       │      9. Переход в ACTIVE режим
│                  │      10. Запуск таймера стабилизации (60 сек)
│ ┌──────────────┐ │      11. Старт измерений pH
│ │ Sensor Mode  │ │
│ │ Manager      │ │
│ └──────────────┘ │
└──────┬───────────┘
       │ 12. Начало публикации телеметрии
       │
       ▼
Topic: hydro/gh-1/zn-1/nd-ph-1/ph_main/telemetry
Payload:
{
  "metric_type": "PH",
  "value": 5.6,
  "ts": 1710001234,
  "flow_active": true,        ◄─── Поток есть (заливка бака)
  "stable": false,            ◄─── Ещё стабилизируется
  "stabilization_progress_sec": 15,
  "corrections_allowed": false ◄─── Коррекция пока запрещена
}
       │
       │ 13. History-logger записывает в telemetry_samples
       │
       ▼
┌──────────────────┐
│ Automation-      │
│ Engine           │ ◄─── 14. Следующая итерация control loop (через 10 сек)
│                  │      15. Проверка state = TANK_FILLING
│ ┌──────────────┐ │      16. Проверка telemetry для зоны 1
│ │ Control Loop │ │
│ └──────────────┘ │
└──────┬───────────┘
       │ 17. SELECT * FROM telemetry_last
       │     WHERE zone_id = 1
       │       AND metric_type IN ('PH', 'EC')
       │
       ▼
┌──────────────────┐
│  PostgreSQL      │
│  telemetry_last  │ ◄─── Result:
│                  │      {
└──────┬───────────┘        "PH": {
       │                      "value": 5.6,
       │                      "flow_active": true,
       │                      "stable": true,        ◄─── Уже стабилизировался
       │                      "corrections_allowed": true
       │                    },
       │                    "EC": {
       ▼                      "value": 1.2,
┌──────────────────┐           "stable": true,
│ Automation-      │           "corrections_allowed": true
│ Engine           │         }
│                  │      }
│ ┌──────────────┐ │
│ │ pH & EC      │ │ ◄─── 18. Проверка corrections_allowed = true
│ │ Controllers  │ │      19. Сравнение:
│ └──────────────┘ │          current_ph = 5.6 < min = 5.8
│                  │          current_ec = 1.2 < min = 1.6
│                  │
│                  │      20. Решения:
│                  │          - pH: нужна коррекция UP
│                  │          - EC: нужна коррекция NPK UP
│                  │
│                  │      21. Расчет доз:
│                  │          ph_dose_ml = (6.0 - 5.6) * ph_k
│                  │          ec_dose_ml = (1.8 - 1.2) * ec_k
└──────┬───────────┘
       │ 22. Отправка команды коррекции pH UP
       │     POST http://history-logger:9300/commands
       │     {
       │       "node_uid": "nd-ph-1",
       │       "channel": "pump_ph_up",
       │       "type": "dose",
       │       "params": {"ml": 2.0},
       │       "context": {
       │         "state": "TANK_FILLING",
       │         "current_ph": 5.6,
       │         "target_ph": 6.0
       │       }
       │     }
       │
       │ 23. Отправка команды коррекции EC (NPK)
       │     POST http://history-logger:9300/commands
       │     {
       │       "node_uid": "nd-ec-1",
       │       "channel": "pump_npk",
       │       "type": "dose",
       │       "params": {"ml": 5.0},
       │       "context": {
       │         "state": "TANK_FILLING",
       │         "correction_type": "NPK",
       │         "current_ec": 1.2,
       │         "target_ec": 1.8
       │       }
       │     }
       │
       ▼
    [ MQTT → ESP32 ] (см. раздел 3.1, шаги 11-20)

       │ 24. После выполнения дозирования ноды отправляют command_response
       │ 25. Automation-engine ждет min_interval_sec (300 сек) перед следующей коррекцией
       │ 26. Цикл повторяется до достижения целевых значений
       │
       │ 27. При достижении target_volume_l и целевых pH/EC:
       │     - Переход TANK_FILLING → TANK_RECIRC (если нужна рециркуляция)
       │     - Или переход TANK_FILLING → READY (если цели достигнуты)
       │     - Деактивация pH/EC нод (deactivate_sensor_mode)
       │
       ▼
Topic: hydro/gh-1/zn-1/nd-ph-1/system/command
Payload: {"cmd": "deactivate_sensor_mode"}

       │ 28. pH/EC ноды переходят в IDLE режим
       │     - Останавливают измерения
       │     - Публикуют только heartbeat и LWT
```

#### 3.3.4. Логика активации/деактивации нод

**Когда активировать:**
- Переход в TANK_FILLING: перед началом заливки бака
- Переход в IRRIGATING: перед началом полива

**Когда деактивировать:**
- Переход в READY: после достижения целей и остановки потока
- Переход в IDLE: после завершения цикла

**Telemetry флаги:**
- `flow_active`: true если есть поток через сенсор
- `stable`: true после истечения stabilization_time_sec
- `corrections_allowed`: true если stable=true И прошло min_interval_sec от последней коррекции

#### 3.3.5. Отличия режимов TANK_FILLING vs IRRIGATING

**TANK_FILLING (NPK + pH):**
- Коррекция концентрированным NPK раствором
- Цель: базовый питательный раствор (N-P-K)
- Используется EC нода с каналом `pump_npk`

**IRRIGATING (Ca/Mg/micro + pH):**
- Коррекция раствором Ca, Mg, микроэлементов
- Цель: финальная корректировка перед поливом
- Используется EC нода с каналом `pump_ca_mg`

**pH коррекция:**
- Присутствует во ВСЕХ режимах
- Всегда использует pH ноду с каналами `pump_ph_up` / `pump_ph_down`

Подробнее: `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`

---

## 4. Централизованная архитектура публикации команд

### 4.1. Диаграмма потока команд

```
┌─────────────┐
│  Scheduler  │
└──────┬──────┘
       │ REST API (9405)
       │ POST /scheduler/task
       │
       ▼
┌─────────────────┐
│ Automation-     │
│ Engine          │
└──────┬──────────┘
       │ REST API (9300)
       │ POST /commands
       │
       ▼
┌─────────────────┐      ┌──────────────┐
│ History-Logger  │◄────►│  PostgreSQL  │
│ (ЕДИНСТВЕННАЯ   │      │  Логирование │
│  точка MQTT)    │      │  commands    │
└──────┬──────────┘      └──────────────┘
       │
       │ MQTT Publish
       │ hydro/{gh}/{zone}/{node}/{channel}/command
       │
       ▼
┌─────────────────┐
│  MQTT Broker    │
└──────┬──────────┘
       │
       │ Subscribe
       │
       ▼
┌─────────────────┐
│  ESP32 Nodes    │
└─────────────────┘
```

### 4.2. Преимущества архитектуры

1. **Централизованное логирование**
   - Все команды логируются в одном месте
   - Единая таблица `commands` в PostgreSQL
   - Упрощенный аудит и отладка

2. **Единая точка валидации**
   - HMAC подпись добавляется в одном месте
   - Валидация форматов команд
   - Rate limiting (если требуется)

3. **Разделение ответственности**
   - Scheduler — планирование
   - Automation-Engine — бизнес-логика
   - History-Logger — транспортный уровень

4. **Мониторинг**
   - Единая точка для Prometheus метрик
   - history-logger экспортирует:
     - `commands_published_total`
     - `commands_failed_total`
     - `mqtt_publish_duration_seconds`

---

## 5. Monitoring и метрики пайплайн

```
┌─────────────────────────────────────────────────────────────┐
│                    Prometheus (9090)                        │
│                                                             │
│  Scrape Targets:                                            │
│  - mqtt-bridge:9000/metrics                                 │
│  - history-logger:9301/metrics                              │
│  - automation-engine:9401/metrics                           │
│  - scheduler:9402/metrics                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Metrics Query
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Grafana (3000)                           │
│                                                             │
│  Dashboards:                                                │
│  ┌──────────────────────┐  ┌──────────────────────┐       │
│  │ System Overview      │  │ Zone Telemetry       │       │
│  │ - Service health     │  │ - pH/EC graphs       │       │
│  │ - MQTT status        │  │ - Temperature        │       │
│  │ - DB connections     │  │ - Humidity           │       │
│  └──────────────────────┘  └──────────────────────┘       │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐       │
│  │ Commands & Automation│  │ Node Status          │       │
│  │ - Commands rate      │  │ - Online/Offline     │       │
│  │ - Success rate       │  │ - Last seen          │       │
│  │ - Task execution     │  │ - RSSI/Battery       │       │
│  └──────────────────────┘  └──────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Ключевые порты и эндпоинты

### 6.1. Сервисы и порты

| Сервис | Порт(ы) | Назначение |
|--------|---------|------------|
| **Laravel** | 8080 | HTTP API, Web UI, WebSocket (Reverb) |
| **MQTT Broker** | 1883 | MQTT pub/sub |
| **PostgreSQL** | 5432 | База данных |
| **mqtt-bridge** | 9000 | REST API, Prometheus metrics |
| **history-logger** | 9300, 9301 | REST API (9300), Prometheus metrics (9301) |
| **automation-engine** | 9401, 9405 | Prometheus metrics (9401), REST API (9405) |
| **scheduler** | 9402 | Prometheus metrics |
| **Prometheus** | 9090 | Метрики и мониторинг |
| **Grafana** | 3000 | Визуализация метрик |

### 6.2. REST API Endpoints

**Laravel (:8080)**
```
POST /api/zones/{id}/commands       - Отправка команды зоне
GET  /api/zones/{id}/telemetry/last - Последняя телеметрия
GET  /api/nodes/{id}/telemetry/last - Последняя телеметрия ноды
```

**history-logger (:9300)**
```
POST /commands                       - Универсальный endpoint команд
POST /zones/{zone_id}/commands       - Команды для зоны
POST /nodes/{node_uid}/commands      - Команды для ноды
GET  /health                         - Health check
```

**automation-engine (:9405)**
```
POST /scheduler/task                 - Прием задачи от scheduler
POST /scheduler/bootstrap            - Инициализация scheduler
GET  /scheduler/task/{task_id}       - Статус задачи
GET  /health                         - Health check
```

### 6.3. MQTT Topics структура

**Telemetry (ESP32 → Backend)**
```
hydro/{greenhouse_uid}/{zone_id}/{node_uid}/{channel}/telemetry

Примеры:
hydro/gh-1/zn-3/nd-ph-1/ph_main/telemetry
hydro/gh-1/zn-3/nd-pump-1/pump_in/telemetry
hydro/gh-1/zn-3/nd-climate-1/temp_air/telemetry
```

**Commands (Backend → ESP32)**
```
hydro/{greenhouse_uid}/{zone_id}/{node_uid}/{channel}/command

Примеры:
hydro/gh-1/zn-1/nd-pump-1/pump_in/command
hydro/gh-1/zn-3/nd-ph-1/pump_ph_up/command
hydro/gh-1/zn-2/nd-light-1/pwm_channel_1/command
```

**Status (ESP32 → Backend)**
```
hydro/{greenhouse_uid}/{zone_id}/{node_uid}/status
hydro/{greenhouse_uid}/{zone_id}/{node_uid}/lwt

Примеры:
hydro/gh-1/zn-1/nd-pump-1/status
hydro/gh-1/zn-1/nd-pump-1/lwt
```

---

## 7. Связанные документы

- `SYSTEM_ARCH_FULL.md` — общая архитектура системы
- `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API спецификация history-logger
- `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол
- `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets

---

**Документ актуален после аудита документации от 2026-02-14**
