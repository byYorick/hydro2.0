# Node Simulator (node-sim)

**ЕДИНСТВЕННЫЙ ТЕСТОВЫЙ СТАНДАРТ** для симуляции нод в системе Hydro 2.0.
Совместим с протоколом MQTT системы. Используется в E2E тестах.

**Важно:** Дублированные реализации удалены. Эта реализация - единственный источник истины для тестирования.

## Установка

```bash
cd tests/node_sim
pip install -r requirements.txt
```

## Использование

### Базовый запуск

```bash
python -m node_sim.cli run --config sim.example.yaml
```

### Запуск сценария

```bash
python -m node_sim.cli scenario --config sim.example.yaml --name S_overcurrent
```

### Множественные ноды (опционально)

```bash
python -m node_sim.cli multi --config multi.yaml
```

## Конфигурация

См. `sim.example.yaml` для примера конфигурации.

### Основные параметры

- `mqtt`: Настройки подключения к MQTT брокеру
- `node`: Идентификаторы ноды (gh_uid, zone_uid, node_uid, hardware_id)
- `telemetry`: Интервалы публикации телеметрии и heartbeat
- `failure_mode`: Режимы отказов для тестирования (опционально)

## Режимы работы

- `preconfig`: Нода еще не привязана к зоне (использует temp-топики)
- `configured`: Нода привязана к зоне (использует обычные топики)

## Функциональность

- ✅ Публикация телеметрии для всех каналов
- ✅ Публикация тока INA209 в телеметрии
- ✅ Публикация heartbeat и online status (в обоих режимах: preconfig/configured)
- ✅ Обработка команд с дедупликацией по cmd_id
- ✅ Отправка command_response (ACCEPTED быстро, DONE/FAILED после выполнения)
- ✅ Мониторинг доставленных команд (cmd_id, тайминги, статистика)
- ✅ Режимы отказов: delay, drop, duplicate, overcurrent, no_flow
- ✅ Поддержка temp-топиков для preconfig режима

## Отказные режимы (Failure Modes)

Node-sim поддерживает несколько режимов отказов для тестирования негативных сценариев:

### 1. Delay Response (Задержка ответа)
Задерживает отправку ответа на команду:
```yaml
failure_mode:
  delay_response: true
  delay_ms: 5000  # Задержка в миллисекундах
```

### 2. Drop Response (Пропуск ответа)
Пропускает отправку ответа на команду (имитация потери пакета):
```yaml
failure_mode:
  drop_response: true
```

### 3. Duplicate Response (Дублирование ответа)
Отправляет ответ дважды (имитация дубликата пакета):
```yaml
failure_mode:
  duplicate_response: true
```

### 4. Overcurrent (Перегрузка по току)
Имитирует режим перегрузки по току - устанавливает высокий ток INA209:
```python
# Через команду hil_set_current
node.set_overcurrent_mode(enabled=True, current=600.0)  # 600 мА
```

### 5. No Flow (Отсутствие потока)
Имитирует отсутствие потока для насосов (для тестирования ошибки biz_no_flow):
```python
# Через команду hil_set_flow или напрямую
node.set_no_flow_mode("main_pump", enabled=True)
```

### Мониторинг команд

Node-sim ведет статистику доставленных команд:
- `total_received` - всего получено команд
- `total_delivered` - успешно доставлено ответов
- `total_dropped` - пропущено ответов
- `total_duplicated` - дублировано ответов
- `total_failed` - провалено команд
- `commands_by_status` - распределение по статусам (DONE, ERROR, etc.)
- `avg_response_time_ms` - среднее время ответа

Получить статистику:
```python
stats = command_handler.get_command_stats()
print(f"Delivered: {stats['total_delivered']}, Avg response time: {stats['avg_response_time_ms']}ms")
```

Логирование включает:
- `cmd_id` для каждой команды
- Тайминги выполнения (execution_time_ms)
- Время ответа (response_time_ms)
- Среднее время ответа

## Структура проекта

```
tests/node_sim/
├── node_sim/
│   ├── __init__.py
│   ├── cli.py          # CLI интерфейс
│   ├── config.py       # Валидатор конфигурации
│   ├── logging.py      # Настройка логирования
│   ├── utils_time.py   # Утилиты для работы со временем
│   ├── mqtt_client.py  # MQTT клиент
│   ├── model.py        # Модель ноды
│   ├── commands.py     # Обработка команд
│   ├── state_machine.py # Машина состояний команд
│   └── telemetry.py    # Публикация телеметрии
├── requirements.txt
├── sim.example.yaml    # Пример конфигурации
└── README.md
```

## Разработка

Для разработки установите зависимости в режиме разработки:

```bash
pip install -r requirements.txt
pip install -e .
```

## Тестирование

```bash
# Проверка подключения к MQTT
python -m node_sim.cli run --config sim.example.yaml --log-level DEBUG
```

## Совместимость

- MQTT протокол системы Hydro 2.0
- Форматы топиков согласно MQTT_SPEC_FULL.md
- Форматы команд и ответов согласно единому контракту

