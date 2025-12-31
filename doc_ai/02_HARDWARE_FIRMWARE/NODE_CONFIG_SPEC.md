# NODE_CONFIG_SPEC.md
# Спецификация NodeConfig для ESP32-нод

Документ описывает структуру и формат NodeConfig — конфигурации узлов ESP32.

**ВАЖНО:** Эталонная версия этого документа находится здесь.  
Копия для разработчиков прошивок: `firmware/NODE_CONFIG_SPEC.md`.

**Связанные документы:**
- `firmware/NODE_CONFIG_SPEC.md` — копия для прошивки
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — архитектура нод
- `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md` — структура прошивки
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и топики
- `doc_ai/01_SYSTEM/DATAFLOW_FULL.md` — потоки данных
- Шаблоны: `configs/nodes/*.json`

---

## 1. Общее описание

NodeConfig — это JSON-конфигурация узла ESP32, которая:
- Формируется в прошивке (жёстко зашита) и сохраняется в NVS
- Определяет тип узла и его каналы (сенсоры/актуаторы)
- Задаёт параметры Wi‑Fi и MQTT
- Устанавливает безопасные лимиты и пороги
- Публикуется нодой на сервер после подключения через MQTT топик `hydro/{gh}/{zone}/{node}/config_report`
- Не редактируется и не отправляется сервером обратно на ноду

---

## 2. Формат и структура

### 2.1. Базовый формат

```json
{
  "node_id": "nd-ph-1",
  "version": 3,
  "type": "ph_node",
  "gh_uid": "gh-1",
  "zone_uid": "zn-3",
  "channels": [],
  "wifi": {...},
  "mqtt": {...},
  "limits": {...},
  "calibration": {...}
}
```

### 2.2. Поля верхнего уровня

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `node_id` | string | Да | Уникальный идентификатор узла (UID) |
| `version` | integer | Да | Версия формата конфигурации |
| `type` | string | Да | Тип узла: `ph_node`, `ec_node`, `climate_node`, `pump_node`, `lighting_node` |
| `gh_uid` | string | Да | Уникальный идентификатор теплицы (Greenhouse UID) |
| `zone_uid` | string | Да | Уникальный идентификатор зоны (Zone UID) |
| `channels` | array | Да | Массив каналов ноды (сенсоры/актуаторы). Каналы формируются в прошивке и отправляются нодой на сервер. |
| `wifi` | object | Да | Параметры Wi-Fi подключения |
| `mqtt` | object | Да | Параметры MQTT подключения |
| `limits` | object | Нет | Безопасные лимиты (ток, время работы и т.д.) |
| `calibration` | object | Нет | Параметры калибровки (pH, EC) |

---

## 3. Детальное описание полей

### 3.1. `node_id`

Уникальный строковый идентификатор узла. Используется в:
- MQTT топиках
- Телеметрии
- Командах

**Примеры:**
- `"nd-ph-1"` — pH-нода #1
- `"nd-ec-2"` — EC-нода #2
- `"pump-001"` — насосная нода #001

### 3.2. `version`

Версия формата конфигурации. При изменении структуры версия увеличивается.

**Текущая версия:** `3`

### 3.3. `type`

Тип узла. Определяет базовое поведение и доступные каналы.

**Возможные значения:**
- `ph_node` — нода измерения pH
- `ec_node` — нода измерения EC (электропроводности)
- `climate_node` — нода климата (температура, влажность, CO₂)
- `pump_node` — нода управления насосами
- `lighting_node` — нода управления освещением

### 3.4. `gh_uid`

Уникальный строковый идентификатор теплицы (Greenhouse UID). Используется в:
- MQTT топиках для маршрутизации сообщений
- Идентификации принадлежности узла к теплице

**Примеры:**
- `"gh-1"` — теплица #1
- `"gh-main"` — главная теплица

### 3.5. `zone_uid`

Уникальный строковый идентификатор зоны (Zone UID). Используется в:
- MQTT топиках для маршрутизации сообщений
- Идентификации принадлежности узла к зоне внутри теплицы

**Примеры:**
- `"zn-3"` — зона #3
- `"zn-main"` — главная зона

### 3.6. `channels`

Поле описывает каналы, зашитые в прошивке. Нода публикует этот список на сервер в составе `config_report`, сервер хранит и использует его для команд и телеметрии.

Массив каналов узла. Каждый канал — это сенсор или актуатор.

#### 3.4.1. Канал сенсора

```json
{
  "name": "ph_sensor",
  "type": "SENSOR",
  "metric": "PH",
  "poll_interval_ms": 3000,
  "unit": "pH",
  "precision": 2
}
```

**Поля:**
- `name` (string, обязательное) — имя канала
- `type` (string, обязательное) — `"SENSOR"`
- `metric` (string, обязательное) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LIGHT_INTENSITY`, `WATER_LEVEL`, `FLOW_RATE`, `PUMP_CURRENT`
- `poll_interval_ms` (integer, обязательное) — интервал опроса в миллисекундах
- `unit` (string, необязательное) — единица измерения
- `precision` (integer, необязательное) — точность (количество знаков после запятой)

#### 3.4.2. Канал актуатора

```json
{
  "name": "pump_acid",
  "type": "ACTUATOR",
  "actuator_type": "PUMP",
  "safe_limits": {
    "max_duration_ms": 5000,
    "min_off_ms": 3000,
    "fail_safe_mode": "NO"
  },
  "channel": "pump_in"
}
```

Пример для реле:

```json
{
  "name": "fan_1",
  "type": "ACTUATOR",
  "actuator_type": "FAN",
  "relay_type": "NO",
  "gpio": 27
}
```

**Поля:**
- `name` (string, обязательное) — имя канала
- `type` (string, обязательное) — `"ACTUATOR"`
- `actuator_type` (string, обязательное) — тип актуатора: `PUMP`, `PERISTALTIC_PUMP`, `RELAY`, `VALVE`, `DRIVE`, `FAN`, `HEATER`, `LED`, `PWM`
- `safe_limits` (object, необязательное) — безопасные лимиты:
  - `max_duration_ms` — максимальная длительность работы в мс
  - `min_off_ms` — минимальное время простоя в мс
  - `fail_safe_mode` — режим НЗ/НО: `NC` или `NO` (для насосов/приводов)
- `relay_type` (string, обязательное для `RELAY`/`VALVE`/`FAN`/`HEATER`) — тип реле: `NC` или `NO`
- `channel` (string, необязательное) — физический канал (для pump_node)

#### 3.4.3. Канал актуатора DRIVE (привод)

```json
{
  "name": "vent_drive",
  "type": "ACTUATOR",
  "actuator_type": "DRIVE",
  "gpio_open": 25,
  "gpio_close": 26,
  "limit_switches": {
    "open_gpio": 32,
    "close_gpio": 33
  },
  "drive": {
    "travel_ms": 15000,
    "position_percent": 0
  },
  "safe_limits": {
    "max_duration_ms": 20000,
    "min_off_ms": 1000,
    "fail_safe_mode": "NO"
  }
}
```

**Поля:**
- `gpio_open` / `gpio_close` (integer, обязательное) — GPIO для направления открытия/закрытия
- `limit_switches.open_gpio` / `limit_switches.close_gpio` (integer, обязательное) — GPIO концевиков
- `drive.travel_ms` (integer, обязательное) — полный ход привода в мс (закрыто → открыто)
- `drive.position_percent` (integer, необязательное) — текущая/начальная позиция (0–100), рассчитывается по `travel_ms`

**Примечание:** команды для привода используют `direction` (OPEN/CLOSE/STOP) и/или `target_percent`, вычисляя время работы от `travel_ms`. Полное открытие/закрытие подтверждается концевиками.

### 3.7. `wifi`

Параметры подключения к Wi-Fi.

```json
{
  "ssid": "HydroFarm",
  "pass": "12345678",
  "auto_reconnect": true,
  "timeout_sec": 30
}
```

**Поля:**
- `ssid` (string, обязательное) — имя сети Wi-Fi
- `pass` (string, обязательное) — пароль Wi-Fi
- `auto_reconnect` (boolean, необязательное) — автоматическое переподключение (по умолчанию: `true`)
- `timeout_sec` (integer, необязательное) — таймаут подключения в секундах (по умолчанию: `30`)

**Примечание:** после первичной настройки допускается присылать `wifi: {"configured": true}` или полностью опускать секцию `wifi`, чтобы сохранить текущие настройки на устройстве.

### 3.8. `mqtt`

Параметры подключения к MQTT брокеру.

```json
{
  "host": "192.168.1.10",
  "port": 1883,
  "keepalive": 30,
  "client_id": "nd-ph-1",
  "user": null,
  "pass": null,
  "tls": false
}
```

**Поля:**
- `host` (string, обязательное) — IP-адрес или hostname MQTT брокера
- `port` (integer, обязательное) — порт MQTT брокера (обычно `1883` или `8883` для TLS)
- `keepalive` (integer, необязательное) — интервал keepalive в секундах (по умолчанию: `30`)
- `client_id` (string, необязательное) — MQTT client ID (по умолчанию: `node_id`)
- `user` (string, необязательное) — имя пользователя для аутентификации
- `pass` (string, необязательное) — пароль для аутентификации
- `tls` (boolean, необязательное) — использование TLS (по умолчанию: `false`)

### 3.9. `limits`

Безопасные лимиты для узла (особенно для pump_node).

```json
{
  "currentMin": 0.1,
  "currentMax": 2.5,
  "max_runtime_sec": 300,
  "cooldown_sec": 60
}
```

**Поля:**
- `currentMin` (float, необязательное) — минимальный ток для обнаружения работы (для INA209)
- `currentMax` (float, необязательное) — максимальный допустимый ток
- `max_runtime_sec` (integer, необязательное) — максимальное время непрерывной работы в секундах
- `cooldown_sec` (integer, необязательное) — время охлаждения после работы в секундах

### 3.10. `calibration`

Параметры калибровки сенсоров (pH, EC).

```json
{
  "ph": {
    "point1": {"raw": 1000, "value": 4.0},
    "point2": {"raw": 2000, "value": 7.0},
    "point3": {"raw": 3000, "value": 10.0}
  },
  "ec": {
    "k_value": 1.0,
    "temperature_compensation": true
  }
}
```

**Поля:**
- `ph` (object, необязательное) — калибровка pH (2-3 точки)
- `ec` (object, необязательное) — калибровка EC (K-значение, компенсация температуры)

---

## 4. Примеры конфигураций

### 4.1. pH-нода

```json
{
  "node_id": "nd-ph-1",
  "type": "ph_node",
  "version": 3,
  "gh_uid": "gh-1",
  "zone_uid": "zn-3",
  "channels": [
    {
      "name": "ph_sensor",
      "type": "SENSOR",
      "metric": "PH",
      "poll_interval_ms": 3000,
      "unit": "pH",
      "precision": 2
    },
    {
      "name": "pump_acid",
      "type": "ACTUATOR",
      "actuator_type": "PERISTALTIC_PUMP",
      "safe_limits": {
        "max_duration_ms": 5000,
        "min_off_ms": 3000,
        "fail_safe_mode": "NO"
      }
    }
  ],
  "wifi": {
    "ssid": "HydroFarm",
    "pass": "12345678"
  },
  "mqtt": {
    "host": "192.168.1.10",
    "port": 1883,
    "keepalive": 30
  },
  "calibration": {
    "ph": {
      "point1": {"raw": 1000, "value": 4.0},
      "point2": {"raw": 2000, "value": 7.0}
    }
  }
}
```

### 4.2. Насосная нода (pump_node)

```json
{
  "node_id": "pump-001",
  "type": "pump_node",
  "version": 3,
  "gh_uid": "gh-1",
  "zone_uid": "zn-3",
  "channels": [
    {
      "name": "pump_in",
      "type": "ACTUATOR",
      "actuator_type": "PUMP",
      "channel": "pump_in",
      "safe_limits": {
        "max_duration_ms": 60000,
        "min_off_ms": 5000,
        "fail_safe_mode": "NO"
      }
    },
    {
      "name": "pump_out",
      "type": "ACTUATOR",
      "actuator_type": "PUMP",
      "channel": "pump_out",
      "safe_limits": {
        "max_duration_ms": 60000,
        "min_off_ms": 5000,
        "fail_safe_mode": "NO"
      }
    }
  ],
  "wifi": {
    "ssid": "HydroFarm",
    "pass": "12345678"
  },
  "mqtt": {
    "host": "192.168.1.10",
    "port": 1883,
    "keepalive": 30
  },
  "limits": {
    "currentMin": 0.1,
    "currentMax": 2.5,
    "max_runtime_sec": 300,
    "cooldown_sec": 60
  }
}
```

### 4.3. Климатическая нода (climate_node)

```json
{
  "node_id": "nd-climate-1",
  "type": "climate_node",
  "version": 3,
  "gh_uid": "gh-1",
  "zone_uid": "zn-3",
  "channels": [
    {
      "name": "temperature",
      "type": "SENSOR",
      "metric": "TEMPERATURE",
      "poll_interval_ms": 5000,
      "unit": "°C",
      "precision": 1
    },
    {
      "name": "humidity",
      "type": "SENSOR",
      "metric": "HUMIDITY",
      "poll_interval_ms": 5000,
      "unit": "%",
      "precision": 1
    },
    {
      "name": "co2",
      "type": "SENSOR",
      "metric": "CO2",
      "poll_interval_ms": 10000,
      "unit": "ppm",
      "precision": 0
    }
  ],
  "wifi": {
    "ssid": "HydroFarm",
    "pass": "12345678"
  },
  "mqtt": {
    "host": "192.168.1.10",
    "port": 1883,
    "keepalive": 30
  }
}
```

---

## 5. Процесс загрузки и применения

### 5.1. При первом запуске

1. Узел загружает NodeConfig из NVS (если есть), иначе использует встроенный (firmware) вариант
2. Если конфигурации нет и нет встроенной — узел переходит в режим provisioning
3. Узел подключается к MQTT и публикует NodeConfig в `hydro/{gh}/{zone}/{node}/config_report`
4. Сервер сохраняет конфигурацию в БД и синхронизирует каналы

### 5.2. При обновлении конфигурации

1. Конфигурация обновляется только через прошивку (или локальный provisioning)
2. После перезапуска узел публикует обновлённый NodeConfig в `config_report`
3. Сервер обновляет сохранённую конфигурацию и каналы

### 5.3. Валидация

Узел должен проверить:
- Наличие обязательных полей (включая `gh_uid` и `zone_uid`)
- Корректность типов данных
- Допустимые значения (порты, интервалы)
- Соответствие типа узла и каналов

При ошибке валидации узел логирует проблему и остаётся на текущей конфигурации.

---

## 6. Хранение в NVS

NodeConfig сохраняется в NVS (Non-Volatile Storage) ESP32:
- Ключ: `node_config`
- Формат: JSON (может быть сжат или сериализован в CBOR)
- Размер: ограничен размером NVS раздела (обычно 4-16 KB)

При загрузке узел:
1. Читает конфигурацию из NVS
2. Парсит JSON
3. Применяет параметры Wi-Fi и MQTT
4. Инициализирует каналы согласно конфигурации

---

## 7. Генерация конфигурации

NodeConfig формируется в прошивке узла и хранится на стороне ноды.
Сервер принимает конфигурацию через `config_report`, сохраняет в БД и использует
для команд, телеметрии и UI.

---

## 8. Версионирование

При изменении структуры NodeConfig:
1. Увеличивается версия формата
2. Обновляется документация
3. Обеспечивается обратная совместимость (если возможно)
4. Узлы с старой версией могут запросить обновление

**Текущая версия:** `3`

---

## 9. Ссылки

- Шаблоны конфигураций: `configs/nodes/*.json`
- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- MQTT протокол: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- Структура прошивки: `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`
- Потоки данных: `doc_ai/01_SYSTEM/DATAFLOW_FULL.md`

---

## 10. Примечания

- NodeConfig формируется в прошивке и публикуется нодой на сервер
- Сервер не редактирует и не отправляет конфиг обратно на ноду
- Обновление конфигурации происходит через обновление прошивки (или локальный provisioning)
- При ошибке применения локальной конфигурации узел остаётся в текущем состоянии и сообщает об ошибке
