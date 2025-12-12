# Node Simulator (node-sim)

Симулятор нод для системы Hydro 2.0. Совместим с протоколом MQTT системы.

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
- ✅ Публикация heartbeat и online status
- ✅ Обработка команд с дедупликацией по cmd_id
- ✅ Отправка command_response (ACCEPTED быстро, DONE/FAILED после выполнения)
- ✅ Режимы отказов: delay, drop, duplicate
- ✅ Поддержка temp-топиков для preconfig режима

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

