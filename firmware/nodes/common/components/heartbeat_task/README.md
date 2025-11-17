# Heartbeat Task Component

Компонент для публикации heartbeat во всех нодах.

## Описание

Общая логика heartbeat задачи согласно MQTT_SPEC_FULL.md раздел 9.2.

## Использование

```c
#include "heartbeat_task.h"

// Запуск с параметрами по умолчанию (15000 мс, приоритет 3, стек 3072)
heartbeat_task_start_default();

// Или с кастомными параметрами
heartbeat_task_start(10000, 5, 4096);
```

## API

- `heartbeat_task_start()` - запуск задачи с параметрами
- `heartbeat_task_start_default()` - запуск с параметрами по умолчанию
- `heartbeat_task_stop()` - остановка задачи

