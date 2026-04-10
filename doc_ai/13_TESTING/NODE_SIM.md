# Node Simulator (node_sim) - Документация

Симулятор узлов для системы Hydro 2.0. Позволяет эмулировать работу реальных устройств через MQTT протокол.

## Быстрый старт

### Установка

```bash
cd tests/node_sim
pip install -r requirements.txt
```

### Простой запуск

```bash
# Запуск с примером конфигурации
python -m node_sim.cli run --config sim.example.yaml

# Запуск с детальным логированием
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

## Конфигурация

### Структура конфигурационного файла

```yaml
mqtt:
  host: localhost              # Хост MQTT брокера
  port: 1883                   # Порт MQTT брокера
  username: null               # Пользователь (опционально)
  password: null               # Пароль (опционально)
  tls: false                   # Использовать TLS
  ca_certs: null               # Путь к CA сертификату
  client_id: null              # Client ID (автогенерируется если null)
  keepalive: 60                # Keepalive интервал

node:
  gh_uid: gh-1                 # UID теплицы
  zone_uid: zn-1               # UID зоны (null для unassigned)
  node_uid: nd-sim-1           # UID узла
  hardware_id: esp32-sim-001   # Hardware ID узла
  node_type: ph                # Тип узла: ph, ec, climate, pump, irrig, light, unknown
  mode: configured             # Режим: preconfig | configured
  channels:                    # Каналы узла
    - ph_sensor
    - solution_temp_c
  actuators:                   # Активаторы узла
    - main_pump
    - drain_pump

telemetry:
  interval_seconds: 5.0                      # Интервал публикации телеметрии
  heartbeat_interval_seconds: 30.0           # Интервал heartbeat
  status_interval_seconds: 60.0              # Интервал статуса (опционально)

failure_mode:                  # Режимы отказов (опционально)
  delay_response: false        # Задержка ответа
  delay_ms: 0                 # Задержка в миллисекундах
  drop_response: false        # Пропуск ответа
  duplicate_response: false   # Дублирование ответа
```

### Переменные окружения

Конфигурация может быть переопределена через переменные окружения:

```bash
MQTT_HOST=localhost           # Переопределение MQTT хоста
MQTT_PORT=1883                # Переопределение порта
MQTT_USER=username            # Пользователь MQTT
MQTT_PASS=password            # Пароль MQTT
NODE_SIM_CONFIG=/path/to/config.yaml  # Путь к конфигурации
```

### Режимы работы узла

#### preconfig

Узел еще не привязан к зоне. Использует временные топики:

```
hydro/gh-temp/zn-temp/{hardware_id}/...
```

Где `{hardware_id}` — hardware_id (или MAC) узла.

Используется для:
- Тестирования регистрации узлов
- Тестирования процесса привязки к зоне
- Эмуляции новых узлов

#### configured

Узел привязан к зоне. Использует обычные топики:

```
hydro/{gh_uid}/{zone_uid}/{node_uid}/...
```

Используется для:
- Тестирования нормальной работы системы
- Эмуляции работы привязанных узлов
- E2E тестов

## Команды CLI

### run

Запуск симулятора одного узла:

```bash
python -m node_sim.cli run --config sim.example.yaml
```

Опции:
- `--config PATH` - путь к конфигурационному файлу (обязательно)
- `--log-level LEVEL` - уровень логирования (DEBUG, INFO, WARNING, ERROR)

### multi

Запуск симулятора множества узлов:

```bash
python -m node_sim.cli multi --config multi.example.yaml
```

Формат конфигурации для multi режима:

```yaml
mqtt:
  host: localhost
  port: 1883

telemetry:
  interval_seconds: 5.0
  heartbeat_interval_seconds: 30.0

nodes:
  - node_uid: nd-ph-1
    hardware_id: esp32-sim-001
    gh_uid: gh-1
    zone_uid: zn-1
    node_type: ph
    mode: configured
    channels:
      - ph_sensor
    actuators:
      - main_pump
  
  - node_uid: nd-ec-1
    hardware_id: esp32-sim-002
    gh_uid: gh-1
    zone_uid: zn-1
    node_type: ec
    mode: configured
    channels:
      - ec_sensor
```

### scenario

Запуск предопределенного сценария:

```bash
python -m node_sim.cli scenario --config sim.example.yaml --name S_overcurrent
```

## Функциональность

### Публикация телеметрии

Симулятор автоматически публикует телеметрию для всех каналов, указанных в конфигурации:

```json
{
  "metric_type": "PH",
  "value": 6.5,
  "ts": 1699123456,
  "unit": "pH"
}
```

Поле `ts` — Unix timestamp в секундах.

Топик: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry`

### Публикация heartbeat

Регулярная публикация heartbeat для поддержания online статуса:

```json
{
  "uptime": 3600,
  "free_heap": 123456,
  "rssi": -55
}
```

Топик: `hydro/{gh_uid}/{zone_uid}/{node_uid}/heartbeat`

### Обработка команд

Симулятор подписывается на топик команд и обрабатывает их:

1. **Получение команды** из топика: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command`
2. **Дедупликация** по `cmd_id`
3. **Отправка ACCEPTED** в топик: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command_response`
4. **Выполнение команды** (симуляция)
5. **Отправка DONE/FAILED** в тот же топик ответов

Пример ответа:

```json
{
  "cmd_id": "cmd-123",
  "status": "DONE",
  "result_code": 0,
  "duration_ms": 8500,
  "ts": 1699123456789
}
```

### Режимы отказов

Для тестирования устойчивости системы можно включить режимы отказов:

```yaml
failure_mode:
  delay_response: true         # Задержка ответа на команды
  delay_ms: 5000              # Задержка 5 секунд
  drop_response: false        # Пропуск ответа (команда теряется)
  duplicate_response: false   # Дублирование ответа
```

## Типы узлов

### ph (pH сенсор)

Каналы:
- `ph_sensor` - значение pH
- `solution_temp_c` - температура раствора

Активаторы:
- `main_pump` - основной насос
- `drain_pump` - дренажный насос

### ec (EC сенсор)

Каналы:
- `ec_sensor` - значение EC
- `solution_temp_c` - температура раствора

Активаторы:
- `main_pump` - основной насос

### climate (Климат)

Каналы:
- `air_temp_c` - температура воздуха
- `air_rh` - относительная влажность
- `co2_ppm` - концентрация CO2
- `lux` - освещенность

Активаторы:
- `fan` - вентилятор
- `heater` - обогреватель
- `light` - освещение
- `mister` - увлажнитель

### pump (Насос)

Активаторы:
- `main_pump` - основной насос
- `drain_pump` - дренажный насос

## Примеры использования

### Тестирование регистрации узла

```yaml
node:
  mode: preconfig
  zone_uid: null  # Узел не привязан к зоне
```

Запуск:
```bash
python -m node_sim.cli run --config preconfig_node.yaml
```

### Тестирование обработки команд

```yaml
node:
  mode: configured
  actuators:
    - main_pump

failure_mode:
  delay_response: false  # Нормальная обработка
```

### Тестирование устойчивости к дубликатам

```yaml
failure_mode:
  duplicate_response: true  # Дублировать ответы
```

### Тестирование таймаутов

```yaml
failure_mode:
  delay_response: true
  delay_ms: 30000  # Задержка больше таймаута команды
```

## Отладка

### Включение детального логирования

```bash
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

### Проверка подключения к MQTT

```bash
# Проверка доступности MQTT брокера
mosquitto_pub -h localhost -p 1883 -t test -m "test"

# Подписка на все топики узла
mosquitto_sub -h localhost -p 1883 -t "hydro/+/+/+/#"
```

### Мониторинг телеметрии

```bash
# Подписка на телеметрию конкретного узла
mosquitto_sub -h localhost -p 1883 -t "hydro/gh-1/zn-1/nd-sim-1/+/telemetry"
```

### Мониторинг команд

```bash
# Подписка на команды
mosquitto_sub -h localhost -p 1883 -t "hydro/gh-1/zn-1/nd-sim-1/+/command"

# Подписка на ответы
mosquitto_sub -h localhost -p 1883 -t "hydro/gh-1/zn-1/nd-sim-1/+/command_response"
```

## Интеграция с E2E тестами

Симулятор узлов используется в E2E тестах через Docker Compose:

```yaml
services:
  node-sim:
    build:
      context: ../../tests/node_sim
    environment:
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
    volumes:
      - ./node-sim-config.yaml:/app/config/sim.yaml:ro
    command: python -m node_sim.cli run --config /app/config/sim.yaml
```

## Структура проекта

```
tests/node_sim/
├── node_sim/
│   ├── __init__.py
│   ├── cli.py              # CLI интерфейс
│   ├── config.py           # Валидация конфигурации
│   ├── logging.py          # Настройка логирования
│   ├── mqtt_client.py      # MQTT клиент
│   ├── model.py            # Модель узла
│   ├── commands.py         # Обработка команд
│   ├── state_machine.py    # Машина состояний команд
│   ├── telemetry.py        # Публикация телеметрии
│   ├── status.py           # Публикация статуса
│   └── errors.py           # Публикация ошибок
├── sim.example.yaml        # Пример конфигурации
├── multi.example.yaml      # Пример multi конфигурации
├── requirements.txt        # Зависимости
└── README.md               # Документация
```

## Типовые проблемы

См. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md#node-sim) для решения типовых проблем с node_sim.

## Дополнительные ресурсы

- [TESTING_OVERVIEW.md](./TESTING_OVERVIEW.md) - Общий обзор тестирования
- [E2E_GUIDE.md](./E2E_GUIDE.md) - Руководство по E2E тестам
- [MQTT_SPEC_FULL.md](../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md) - Спецификация MQTT протокола
- [BACKEND_NODE_CONTRACT_FULL.md](../../doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md) - Контракт между backend и узлами
