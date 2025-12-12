# E2E Test Runner Framework

Единый раннер YAML сценариев с проверками API/DB/WS/MQTT для Hydro 2.0.

## Структура

```
tests/e2e/
├── runner/
│   ├── __init__.py
│   ├── e2e_runner.py      # Основной раннер
│   ├── api_client.py      # HTTP клиент для API
│   ├── ws_client.py       # WebSocket клиент (Reverb)
│   ├── db_probe.py        # Проверки базы данных
│   ├── mqtt_probe.py      # Проверки MQTT
│   ├── assertions.py     # Кастомные assertions
│   └── reporting.py      # Генерация отчетов
├── scenarios/
│   └── E02_command_happy.yaml  # Пример сценария
├── reports/               # Генерируемые отчеты
│   ├── junit.xml
│   └── timeline.json
└── requirements.txt
```

## Установка

```bash
cd tests/e2e
pip install -r requirements.txt
```

## Использование

### Базовый запуск

```bash
python tests/e2e/runner/e2e_runner.py tests/e2e/scenarios/E02_command_happy.yaml
```

### Переменные окружения

```bash
export LARAVEL_URL=http://localhost:8080
export LARAVEL_API_TOKEN=your-token
export REVERB_URL=ws://localhost:6001
export DB_DATABASE=/path/to/database.sqlite
export MQTT_HOST=localhost
export MQTT_PORT=1883
export MQTT_USER=username  # опционально
export MQTT_PASS=password  # опционально

python tests/e2e/runner/e2e_runner.py tests/e2e/scenarios/E02_command_happy.yaml
```

## Формат YAML сценариев

### Структура сценария

```yaml
name: Test Scenario Name
description: Описание сценария

steps:
  - name: Step name
    api.get:
      path: /api/endpoint
      params:
        key: value
      save: response_var  # Сохранить результат в переменную

  - name: Subscribe to WebSocket
    ws.subscribe:
      channel: private-commands.1

  - name: Wait for event
    ws.wait_event:
      event: CommandStatusUpdated
      timeout: 10.0

  - name: Check database
    db.wait:
      query: SELECT * FROM commands WHERE id = :id
      params:
        id: 1
      timeout: 5.0
      expected_rows: 1
      save: command_data

  - name: Assert
    assert.equals:
      actual: ${command_data[0].status}
      expected: DONE
```

### Типы шагов

#### API шаги

- `api.get` - GET запрос
- `api.post` - POST запрос
- `api.put` - PUT запрос
- `api.delete` - DELETE запрос

#### WebSocket шаги

- `ws.subscribe` - Подписка на канал
- `ws.wait_event` - Ожидание события

#### Database шаги

- `db.wait` - Ожидание выполнения SQL запроса с условием
- `db.query` - Выполнение SQL запроса

#### MQTT шаги

- `mqtt.subscribe` - Подписка на топик
- `mqtt.wait_message` - Ожидание сообщения

#### Assertions

- `assert.equals` - Проверка равенства
- `assert.contains` - Проверка наличия элемента
- `assert.monotonic_command_status` - Проверка монотонности статусов команд
- `assert.alert_dedup_count` - Проверка количества дубликатов алертов
- `assert.unassigned_present` - Проверка наличия непривязанных узлов
- `assert.attached` - Проверка наличия привязанных узлов

#### Другие шаги

- `set` - Установка переменных в контекст
- `sleep` - Задержка (в секундах)
- `snapshot.fetch` - Получение снимка состояния зоны
- `events.replay` - Воспроизведение событий из снимка

### Переменные

Поддерживается использование переменных в формате `${var}` или `{{var}}`:

```yaml
- name: Use variable
  api.get:
    path: /api/nodes/${node_id}/status
```

Доступ к вложенным полям и индексам:

```yaml
- name: Use nested variable
  set:
    node_id: ${nodes.data[0].id}
    zone_id: ${zones.data[0].zone_id}
```

## Отчеты

После выполнения сценария генерируются отчеты в `tests/e2e/reports/`:

- `junit.xml` - JUnit XML отчет для CI/CD
- `timeline.json` - JSON timeline с детальной информацией о выполнении

### Артефакты

В JSON timeline включаются последние 50 сообщений:
- WebSocket сообщения
- MQTT сообщения
- API ответы

## Примеры

### Пример 1: Проверка статуса команды

```yaml
name: Command Status Check

steps:
  - name: Send command
    api.post:
      path: /api/nodes/1/commands
      json:
        cmd: get_status
        params: {}
      save: command_response

  - name: Get command ID
    set:
      cmd_id: ${command_response.data.cmd_id}

  - name: Wait for status update
    ws.wait_event:
      event: CommandStatusUpdated
      timeout: 10.0

  - name: Check status in DB
    db.wait:
      query: SELECT status FROM commands WHERE cmd_id = :cmd_id
      params:
        cmd_id: ${cmd_id}
      timeout: 5.0
      expected_rows: 1
      save: command_status

  - name: Assert status is DONE
    assert.equals:
      actual: ${command_status[0].status}
      expected: DONE
```

## DoD

✅ Запуск: `python tests/e2e/runner/e2e_runner.py tests/e2e/scenarios/E02_command_happy.yaml`  
✅ На выходе: `tests/e2e/reports/junit.xml`  
✅ Поддержка шагов: `api.post|get|put`, `ws.subscribe/wait_event`, `db.wait`, `assert.*`  
✅ Отчеты: JUnit XML + JSON timeline + артефакты (последние 50 WS/MQTT сообщений)
