Нода насосов (pump_node). Проект ESP-IDF.

## Статус

Скелет создан, реализация в процессе.

## Структура

- `main/` — основной код:
  - `main.c` — точка входа
  - `pump_node_app.c` — логика приложения
  - `pump_node_tasks.c` — FreeRTOS задачи
- `sdkconfig.defaults` — настройки ESP-IDF
- `CMakeLists.txt` — система сборки
- `Kconfig` — конфигурация через menuconfig

## Функционал

Согласно документации, pump_node должна:
- Управлять насосами через реле/драйверы
- Измерять ток через INA209
- Подтверждать выполнение команд через ток
- Отправлять ACK/ERROR в зависимости от тока
- Переходить в SAFE_MODE при критических ошибках

## Документация

- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- Логика нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md`
- INA209 задача: `doc_ai/02_HARDWARE_FIRMWARE/TASK_INA209_PUMP_NODE.md`
- MQTT протокол: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- NodeConfig: `../NODE_CONFIG_SPEC.md`


