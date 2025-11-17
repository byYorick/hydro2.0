# NODE_CONFIG_SPEC.md
# Спецификация NodeConfig для ESP32-нод

Документ описывает структуру и формат NodeConfig — конфигурации узлов ESP32.

**Связанные документы:**
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — архитектура нод
- `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md` — структура прошивки
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и топики
- `doc_ai/01_SYSTEM/DATAFLOW_FULL.md` — потоки данных
- Шаблоны: `configs/nodes/*.json`

---

## 1. Общее описание

NodeConfig — это JSON-конфигурация узла ESP32, которая:
- Определяет тип узла и его каналы (сенсоры/актуаторы)
- Задаёт параметры Wi-Fi и MQTT
- Устанавливает безопасные лимиты и пороги
- Хранится в NVS (Non-Volatile Storage) на узле
- Может быть обновлена через MQTT топик `hydro/{gh}/{zone}/{node}/config`

---

## 2. Формат и структура

### 2.1. Базовый формат

```json
{
  "node_id": "nd-ph-1",
  "version": 3,
  "type": "ph_node",
  "channels": [...],
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
| `channels` | array | Да | Массив каналов (сенсоры и актуаторы) |
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

### 3.4. `channels`

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
- `metric` (string, обязательное) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LUX`
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
    "min_off_ms": 3000
  },
  "channel": "pump_in"
}
```

**Поля:**
- `name` (string, обязательное) — имя канала
- `type` (string, обязательное) — `"ACTUATOR"`
- `actuator_type` (string, обязательное) — тип актуатора: `PUMP`, `VALVE`, `FAN`, `HEATER`, `RELAY`, `LED`
- `safe_limits` (object, необязательное) — безопасные лимиты:
  - `max_duration_ms` — максимальная длительность работы в мс
  - `min_off_ms` — минимальное время простоя в мс
- `channel` (string, необязательное) — физический канал (для pump_node)

### 3.5. `wifi`

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

### 3.6. `mqtt`

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

### 3.7. `limits`

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

### 3.8. `calibration`

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
  "nodeId": "nd-ph-1",
  "type": "ph_node",
  "version": 3,
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
      "actuator_type": "PUMP",
      "safe_limits": {
        "max_duration_ms": 5000,
        "min_off_ms": 3000
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
  "nodeId": "pump-001",
  "type": "pump_node",
  "version": 3,
  "channels": [
    {
      "name": "pump_in",
      "type": "ACTUATOR",
      "actuator_type": "PUMP",
      "channel": "pump_in",
      "safe_limits": {
        "max_duration_ms": 60000,
        "min_off_ms": 5000
      }
    },
    {
      "name": "pump_out",
      "type": "ACTUATOR",
      "actuator_type": "PUMP",
      "channel": "pump_out",
      "safe_limits": {
        "max_duration_ms": 60000,
        "min_off_ms": 5000
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
  "nodeId": "nd-climate-1",
  "type": "climate_node",
  "version": 3,
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

1. Узел загружает NodeConfig из NVS (если есть)
2. Если конфигурации нет, узел переходит в режим provisioning
3. Backend отправляет конфигурацию через MQTT топик `hydro/{gh}/{zone}/{node}/config`
4. Узел сохраняет конфигурацию в NVS
5. Узел отправляет `config_response` с подтверждением

### 5.2. При обновлении конфигурации

1. Backend публикует новую конфигурацию в топик `hydro/{gh}/{zone}/{node}/config`
2. Узел получает конфигурацию
3. Узел валидирует конфигурацию
4. Узел сохраняет в NVS
5. Узел перезапускает каналы согласно новой конфигурации
6. Узел отправляет `config_response` с результатом

### 5.3. Валидация

Узел должен проверить:
- Наличие обязательных полей
- Корректность типов данных
- Допустимые значения (порты, интервалы)
- Соответствие типа узла и каналов

При ошибке валидации узел отправляет `config_response` с `status: "ERROR"`.

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

Backend генерирует NodeConfig на основе:
- Данных из БД (таблицы `nodes`, `node_channels`)
- Шаблонов из `configs/nodes/*.json`
- Параметров зоны и теплицы

Инструменты генерации:
- `tools/gen_node_config/gen_node_config.py` — скрипт генерации
- Laravel API — генерация через `/api/nodes/{id}/config`

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

- NodeConfig полностью формируется на backend
- Узел не имеет собственной логики конфигурации — всё определяется конфигом
- Конфигурация может быть обновлена "на лету" через MQTT
- При ошибке применения конфигурации узел остаётся в текущем состоянии и отправляет ошибку

