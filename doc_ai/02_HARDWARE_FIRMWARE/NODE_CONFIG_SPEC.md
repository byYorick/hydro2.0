# NODE_CONFIG_SPEC.md
# Спецификация NodeConfig для узлов ESP32

Документ описывает структуру и формат конфигурации узлов (NodeConfig), которая загружается из NVS и используется для настройки работы узла.

**Связанные документы:**
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — полная архитектура узлов
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md` — логика работы узлов
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол

---

## 1. Общие принципы

1. **NodeConfig полностью формируется на backend** и передается узлу через MQTT топик `config`
2. **Узел сохраняет конфигурацию в NVS** при первом получении или обновлении
3. **При загрузке узла** конфигурация читается из NVS
4. **Валидация конфигурации** выполняется на узле перед применением
5. **Ответ на config** публикуется в топик `config_response` с результатом (OK/ERROR)

---

## 2. Структура NodeConfig (JSON)

```json
{
  "node_id": "nd-ph-001",
  "type": "ph",
  "version": "1.0.0",
  "greenhouse_uid": "gh-1",
  "zone_id": 3,
  "mqtt": {
    "host": "192.168.1.100",
    "port": 1883,
    "keepalive": 60,
    "user": "hydro",
    "pass": "hydro123",
    "tls": false,
    "topic_prefix": "hydro/gh-1/zn-3"
  },
  "channels": [
    {
      "channel_id": "ph_main",
      "name": "pH Main Sensor",
      "type": "sensor",
      "sensor_type": "ph",
      "poll_interval_ms": 5000,
      "calibration": {
        "points": [
          {"ph": 4.0, "voltage": 1.2},
          {"ph": 7.0, "voltage": 2.1},
          {"ph": 10.0, "voltage": 3.0}
        ],
        "method": "linear"
      },
      "limits": {
        "min": 4.0,
        "max": 10.0,
        "warning_low": 5.5,
        "warning_high": 7.5
      }
    }
  ],
  "hardware": {
    "i2c": {
      "sda": 21,
      "scl": 22,
      "speed": 100000
    },
    "gpio": {
      "pump_control": 4,
      "led_status": 2
    },
    "ina209": {
      "address": 0x40,
      "shunt_resistance_ohm": 0.1,
      "max_current_ma": 5000
    }
  },
  "safety": {
    "max_pump_duration_ms": 30000,
    "min_pump_off_time_ms": 5000,
    "watchdog_timeout_ms": 60000,
    "stabilization_delay_ms": 200
  },
  "telemetry": {
    "heartbeat_interval_ms": 15000,
    "telemetry_interval_ms": 5000,
    "batch_size": 10
  },
  "wifi": {
    "ssid": "HydroFarm",
    "password": "secure_password",
    "reconnect_attempts": 5,
    "reconnect_delay_ms": 5000
  }
}
```

---

## 3. Описание полей

### 3.1. Основные поля

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `node_id` | string | Уникальный идентификатор узла (например, "nd-ph-001") | Да |
| `type` | string | Тип узла: "ph", "ec", "climate", "irrigation", "lighting" | Да |
| `version` | string | Версия конфигурации (семантическое версионирование) | Да |
| `greenhouse_uid` | string | UID теплицы | Да |
| `zone_id` | integer | ID зоны | Да |

### 3.2. MQTT конфигурация

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `mqtt.host` | string | Хост MQTT брокера | Да |
| `mqtt.port` | integer | Порт MQTT брокера (обычно 1883 или 8883 для TLS) | Да |
| `mqtt.keepalive` | integer | Keepalive интервал в секундах | Да |
| `mqtt.user` | string | Имя пользователя MQTT | Нет |
| `mqtt.pass` | string | Пароль MQTT | Нет |
| `mqtt.tls` | boolean | Использовать TLS | Нет (по умолчанию: false) |
| `mqtt.topic_prefix` | string | Префикс для MQTT топиков | Да |

### 3.3. Каналы (channels)

Каждый канал описывает один сенсор или актуатор:

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `channel_id` | string | Уникальный ID канала | Да |
| `name` | string | Человекочитаемое имя | Нет |
| `type` | string | Тип: "sensor" или "actuator" | Да |
| `sensor_type` | string | Для сенсоров: "ph", "ec", "temp", "humidity", "co2" | Для сенсоров |
| `actuator_type` | string | Для актуаторов: "pump", "valve", "relay", "pwm" | Для актуаторов |
| `poll_interval_ms` | integer | Интервал опроса сенсора (для sensor) | Для сенсоров |
| `calibration` | object | Данные калибровки | Нет |
| `limits` | object | Минимальные/максимальные значения и пороги предупреждений | Нет |

#### Калибровка (calibration)

```json
{
  "points": [
    {"ph": 4.0, "voltage": 1.2},
    {"ph": 7.0, "voltage": 2.1},
    {"ph": 10.0, "voltage": 3.0}
  ],
  "method": "linear"
}
```

- `points` — массив точек калибровки
- `method` — метод интерполяции: "linear", "polynomial", "spline"

#### Лимиты (limits)

```json
{
  "min": 4.0,
  "max": 10.0,
  "warning_low": 5.5,
  "warning_high": 7.5
}
```

### 3.4. Аппаратная конфигурация (hardware)

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `hardware.i2c` | object | Конфигурация I²C шины | Нет |
| `hardware.gpio` | object | Назначение GPIO пинов | Нет |
| `hardware.ina209` | object | Конфигурация INA209 (для pump_node) | Нет |

#### I²C конфигурация

```json
{
  "sda": 21,
  "scl": 22,
  "speed": 100000
}
```

#### GPIO конфигурация

```json
{
  "pump_control": 4,
  "led_status": 2,
  "relay_1": 5,
  "relay_2": 6
}
```

#### INA209 конфигурация (для pump_node)

```json
{
  "address": 0x40,
  "shunt_resistance_ohm": 0.1,
  "max_current_ma": 5000,
  "min_bus_current_on": 100,
  "max_bus_current_on": 4500
}
```

### 3.5. Безопасность (safety)

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `safety.max_pump_duration_ms` | integer | Максимальная длительность работы насоса | Для pump_node |
| `safety.min_pump_off_time_ms` | integer | Минимальное время простоя насоса | Для pump_node |
| `safety.watchdog_timeout_ms` | integer | Таймаут watchdog таймера | Нет |
| `safety.stabilization_delay_ms` | integer | Задержка стабилизации после включения (для проверки тока) | Для pump_node |

### 3.6. Телеметрия (telemetry)

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `telemetry.heartbeat_interval_ms` | integer | Интервал отправки heartbeat | Нет (по умолчанию: 15000) |
| `telemetry.telemetry_interval_ms` | integer | Интервал отправки телеметрии | Нет (по умолчанию: 5000) |
| `telemetry.batch_size` | integer | Размер батча для батчинга телеметрии | Нет |

### 3.7. Wi-Fi конфигурация (wifi)

| Поле | Тип | Описание | Обязательное |
|------|-----|----------|--------------|
| `wifi.ssid` | string | SSID сети Wi-Fi | Да |
| `wifi.password` | string | Пароль Wi-Fi | Нет (для открытых сетей) |
| `wifi.reconnect_attempts` | integer | Количество попыток переподключения | Нет (по умолчанию: 5) |
| `wifi.reconnect_delay_ms` | integer | Задержка между попытками переподключения | Нет (по умолчанию: 5000) |

---

## 4. Жизненный цикл конфигурации

### 4.1. Первоначальная загрузка

1. Узел загружается
2. Пытается прочитать NodeConfig из NVS
3. Если конфигурации нет в NVS:
   - Подключается к Wi-Fi (используя дефолтные или hardcoded параметры)
   - Подключается к MQTT
   - Публикует запрос конфигурации в топик `hydro/{gh}/config_request`
   - Ожидает конфигурацию в топике `hydro/{gh}/{zone}/{node}/config`
4. При получении конфигурации:
   - Валидирует конфигурацию
   - Сохраняет в NVS
   - Применяет конфигурацию
   - Публикует `config_response` с статусом OK
5. Backend обрабатывает `config_response`:
   - При `status: "OK"`: если нода была привязана к зоне, переводит в `ASSIGNED_TO_ZONE`
   - При `status: "ERROR"`: нода остается в `REGISTERED_BACKEND`

### 4.2. Обновление конфигурации

1. Backend публикует новую конфигурацию в топик `hydro/{gh}/{zone}/{node}/config`
2. Узел получает конфигурацию
3. Валидирует конфигурацию
4. Если валидация успешна:
   - Сохраняет в NVS
   - Применяет новую конфигурацию
   - Публикует `config_response` с статусом OK
5. Если валидация не прошла:
   - Публикует `config_response` с статусом ERROR и описанием ошибки
   - Продолжает работать со старой конфигурацией
6. Backend обрабатывает `config_response`:
   - При `status: "OK"`: если нода была привязана к зоне и находится в `REGISTERED_BACKEND`, переводит в `ASSIGNED_TO_ZONE`
   - При `status: "ERROR"`: нода остается в текущем состоянии

### 4.3. Формат config_response

```json
{
  "status": "OK",
  "version": "1.0.0",
  "hash": "abc123def456",
  "ts": 1710001234
}
```

Или при ошибке:

```json
{
  "status": "ERROR",
  "version": "1.0.0",
  "hash": "abc123def456",
  "error": "Invalid calibration points",
  "ts": 1710001234
}
```

---

## 5. Валидация конфигурации

Узел должен проверять:

1. **Обязательные поля** присутствуют
2. **Типы данных** соответствуют спецификации
3. **Диапазоны значений** в допустимых пределах:
   - `mqtt.port` в диапазоне 1-65535
   - `poll_interval_ms` > 0
   - `max_pump_duration_ms` > 0 и < 300000 (5 минут максимум)
4. **Калибровка**:
   - Количество точек калибровки >= 2
   - Значения в допустимых диапазонах
5. **GPIO пины** не конфликтуют
6. **I²C адреса** валидны (0x08-0x77)

---

## 6. Хранение в NVS

### 6.1. Структура NVS

- Namespace: `node_config`
- Ключи:
  - `config_json` — полный JSON конфигурации
  - `version` — версия конфигурации
  - `hash` — хеш конфигурации (для проверки изменений)

### 6.2. Размер

Максимальный размер NodeConfig: **4 KB** (ограничение NVS)

Если конфигурация превышает 4 KB, необходимо:
- Оптимизировать структуру
- Использовать сжатие
- Разделить на несколько namespace

---

## 7. Примеры конфигураций

### 7.1. pH node

```json
{
  "node_id": "nd-ph-001",
  "type": "ph",
  "version": "1.0.0",
  "greenhouse_uid": "gh-1",
  "zone_id": 3,
  "mqtt": {
    "host": "192.168.1.100",
    "port": 1883,
    "keepalive": 60,
    "topic_prefix": "hydro/gh-1/zn-3"
  },
  "channels": [
    {
      "channel_id": "ph_main",
      "name": "pH Main Sensor",
      "type": "sensor",
      "sensor_type": "ph",
      "poll_interval_ms": 5000,
      "calibration": {
        "points": [
          {"ph": 4.0, "voltage": 1.2},
          {"ph": 7.0, "voltage": 2.1},
          {"ph": 10.0, "voltage": 3.0}
        ],
        "method": "linear"
      },
      "limits": {
        "min": 4.0,
        "max": 10.0,
        "warning_low": 5.5,
        "warning_high": 7.5
      }
    }
  ],
  "hardware": {
    "i2c": {
      "sda": 21,
      "scl": 22,
      "speed": 100000
    }
  },
  "telemetry": {
    "heartbeat_interval_ms": 15000,
    "telemetry_interval_ms": 5000
  },
  "wifi": {
    "ssid": "HydroFarm",
    "password": "secure_password"
  }
}
```

### 7.2. Pump node

```json
{
  "node_id": "nd-pump-001",
  "type": "irrigation",
  "version": "1.0.0",
  "greenhouse_uid": "gh-1",
  "zone_id": 3,
  "mqtt": {
    "host": "192.168.1.100",
    "port": 1883,
    "keepalive": 60,
    "topic_prefix": "hydro/gh-1/zn-3"
  },
  "channels": [
    {
      "channel_id": "pump_main",
      "name": "Main Pump",
      "type": "actuator",
      "actuator_type": "pump"
    }
  ],
  "hardware": {
    "gpio": {
      "pump_control": 4
    },
    "ina209": {
      "address": 0x40,
      "shunt_resistance_ohm": 0.1,
      "max_current_ma": 5000,
      "min_bus_current_on": 100,
      "max_bus_current_on": 4500
    }
  },
  "safety": {
    "max_pump_duration_ms": 30000,
    "min_pump_off_time_ms": 5000,
    "stabilization_delay_ms": 200
  },
  "telemetry": {
    "heartbeat_interval_ms": 15000
  },
  "wifi": {
    "ssid": "HydroFarm",
    "password": "secure_password"
  }
}
```

---

## 8. Миграция и обратная совместимость

1. **Версионирование** — поле `version` используется для отслеживания изменений
2. **Обратная совместимость** — старые версии конфигурации должны поддерживаться
3. **Миграция** — при обновлении версии узел может автоматически мигрировать старую конфигурацию

---

## 9. Ссылки

- Архитектура узлов: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- Логика узлов: `doc_ai/02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md`
- MQTT протокол: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

