# Android Grow Cycle UI Specification

**Версия:** 1.0  
**Дата:** 2025-01-XX  
**Цель:** Спецификация UI и API контрактов для поддержки Grow Cycle в Android приложении

---

## Содержание

1. [Обзор](#обзор)
2. [Экраны](#экраны)
3. [API Endpoints](#api-endpoints)
4. [DTO Contracts](#dto-contracts)
5. [Синхронизация данных](#синхронизация-данных)
6. [События и WebSocket](#события-и-websocket)

---

## Обзор

Grow Cycle (цикл выращивания) — это основной объект для отображения процесса выращивания в зоне. Каждая зона может иметь один активный цикл в статусах: `PLANNED`, `RUNNING`, `PAUSED`. Завершенные циклы имеют статусы: `HARVESTED`, `ABORTED`.

### Статусы Grow Cycle

- `PLANNED` — цикл запланирован, но еще не запущен
- `RUNNING` — цикл активен и выполняется
- `PAUSED` — цикл приостановлен
- `HARVESTED` — урожай собран, цикл завершен
- `ABORTED` — цикл прерван, завершен

---

## Экраны

### 1. Dashboard Greenhouse

**Путь:** `/greenhouses/{id}/dashboard`

**Описание:** Главный экран теплицы с обзором всех зон и их активных циклов.

**Компоненты:**

1. **Список зон** с информацией:
   - Название зоны
   - Статус зоны (online/offline/warning)
   - Активный Grow Cycle (если есть):
     - Статус цикла (RUNNING/PAUSED/PLANNED)
     - Текущая стадия (stage)
     - Прогресс цикла (%)
     - Дата посадки
     - Ожидаемая дата сбора урожая
   - Последние значения телеметрии (pH, EC, температура, влажность)
   - Количество активных алертов
   - Количество онлайн/офлайн устройств

2. **Фильтры:**
   - По статусу зоны
   - По статусу цикла
   - По наличию алертов

3. **Действия:**
   - Переход к деталям зоны
   - Быстрые действия для цикла (pause/resume)

**API Endpoint:** `GET /api/greenhouses/{greenhouse}/dashboard`

---

### 2. Zone Details

**Путь:** `/zones/{id}`

**Описание:** Детальный экран зоны с полной информацией о текущем цикле.

**Компоненты:**

1. **Заголовок зоны:**
   - Название
   - Статус (online/offline/warning)
   - Количество устройств

2. **Активный Grow Cycle (если есть):**
   - Статус цикла с визуальным индикатором
   - Прогресс-бар общего прогресса
   - Текущая стадия (stage) с прогрессом
   - Дата посадки
   - Ожидаемая дата сбора урожая
   - Настройки цикла (плотность, субстрат и т.д.)
   - Batch label (если задан)

3. **Timeline стадий:**
   - Горизонтальный/вертикальный timeline всех стадий
   - Визуальное отображение: UPCOMING / ACTIVE / DONE
   - Прогресс каждой стадии в %

4. **Текущие значения телеметрии:**
   - pH, EC, температура, влажность, CO2
   - Время последнего обновления

5. **Активные алерты:**
   - Список активных алертов с типами и деталями
   - Кнопка перехода к списку всех алертов

6. **Действия:**
   - Pause/Resume цикл (если RUNNING/PAUSED)
   - Harvest (завершить цикл)
   - Abort (прервать цикл)
   - Change Recipe (сменить рецепт)
   - Advance Stage (перейти на следующую стадию)

**API Endpoint:** `GET /api/zones/{zone}/grow-cycle`

---

### 3. Grow Cycle Timeline

**Путь:** `/zones/{id}/grow-cycle/timeline`

**Описание:** Детальный экран timeline цикла с визуализацией всех стадий.

**Компоненты:**

1. **Временная шкала:**
   - Вертикальный timeline с датами
   - Все стадии рецепта с их длительностью
   - Текущая позиция (сегодня)
   - Визуальное отображение прогресса каждой стадии

2. **Информация о стадиях:**
   - Название стадии
   - Код стадии (code)
   - Даты начала и окончания
   - Прогресс в %
   - Состояние: UPCOMING / ACTIVE / DONE
   - Связанные фазы рецепта (phase_indices)

3. **Детали цикла:**
   - Растение (plant)
   - Рецепт (recipe)
   - Настройки (settings)
   - Заметки (notes)

4. **Действия:**
   - Advance Stage (переход на следующую стадию)
   - Change Recipe (смена рецепта)

**API Endpoint:** `GET /api/zones/{zone}/grow-cycle` (расширенный DTO с timeline)

---

### 4. Alerts

**Путь:** `/zones/{id}/alerts`

**Описание:** Список алертов зоны, связанных с циклом.

**Компоненты:**

1. **Фильтры:**
   - По статусу (ACTIVE/RESOLVED)
   - По типу алерта
   - По дате создания

2. **Список алертов:**
   - Тип алерта (type)
   - Код алерта (code)
   - Детали (details)
   - Статус
   - Дата создания
   - Связь с циклом (если есть)

3. **Действия:**
   - Разрешить алерт (resolve)
   - Перейти к деталям зоны

**API Endpoint:** `GET /api/zones/{zone}/alerts` (существующий endpoint)

---

### 5. Commands

**Путь:** `/zones/{id}/commands`

**Описание:** История команд, отправленных в зону (включая команды управления циклом).

**Компоненты:**

1. **Фильтры:**
   - По статусу команды
   - По типу команды
   - По устройству (node)
   - По дате

2. **Список команд:**
   - ID команды
   - Команда (cmd)
   - Параметры (params)
   - Статус (sent/ack/failed)
   - Устройство (node_id, channel)
   - Время отправки/подтверждения/ошибки
   - Результат (если есть)

3. **Связанные команды цикла:**
   - Команды pause/resume/harvest/abort
   - Команды управления стадиями

**API Endpoint:** `GET /api/zones/{zone}/snapshot` (включает `commands_recent`)

---

## API Endpoints

### Base URL

```
https://api.example.com/api
```

### Authentication

Все запросы требуют Bearer token в заголовке:

```
Authorization: Bearer {token}
```

---

### 1. GET /greenhouses/{greenhouse}/dashboard

**Описание:** Получить dashboard теплицы с информацией о зонах и их циклах.

**Query Parameters:**
- Нет

**Response:**

```json
{
  "status": "ok",
  "data": {
    "greenhouse": {
      "id": 1,
      "name": "Теплица #1",
      "uid": "gh-001"
    },
    "zones": [
      {
        "id": 5,
        "name": "Зона A",
        "status": "online",
        "nodes_total": 10,
        "nodes_online": 9,
        "alerts_count": 2,
        "telemetry": {
          "ph": 6.5,
          "ec": 1.8,
          "temperature": 25.0,
          "humidity": 60.0,
          "co2": 400.0
        },
        "alerts": [
          {
            "id": 100,
            "type": "TEMP_HIGH",
            "code": "biz_high_temp",
            "details": {"message": "Temperature too high"},
            "created_at": "2025-01-15T10:00:00Z"
          }
        ],
        "grow_cycle": {
          "id": 20,
          "status": "RUNNING",
          "current_stage": {
            "code": "VEGETATION",
            "name": "Вегетация"
          },
          "progress": {
            "overall_pct": 45.5,
            "stage_pct": 60.0
          },
          "planting_at": "2025-01-01T08:00:00Z",
          "expected_harvest_at": "2025-02-15T08:00:00Z"
        },
        "recipe_instance": {
          "id": 30,
          "recipe": {
            "id": 10,
            "name": "Рецепт томатов"
          },
          "current_phase_index": 2
        }
      }
    ]
  }
}
```

---

### 2. GET /zones/{zone}/grow-cycle

**Описание:** Получить активный цикл зоны с полной информацией для UI.

**Query Parameters:**
- Нет

**Response:**

```json
{
  "status": "ok",
  "data": {
    "cycle": {
      "id": 20,
      "status": "RUNNING",
      "planting_at": "2025-01-01T08:00:00Z",
      "expected_harvest_at": "2025-02-15T08:00:00Z",
      "current_stage": {
        "code": "VEGETATION",
        "name": "Вегетация",
        "started_at": "2025-01-10T08:00:00Z"
      },
      "progress": {
        "overall_pct": 45.5,
        "stage_pct": 60.0
      },
      "stages": [
        {
          "code": "GERMINATION",
          "name": "Проращивание",
          "from": "2025-01-01T08:00:00Z",
          "to": "2025-01-10T08:00:00Z",
          "pct": 100.0,
          "state": "DONE",
          "phase_indices": [0, 1]
        },
        {
          "code": "VEGETATION",
          "name": "Вегетация",
          "from": "2025-01-10T08:00:00Z",
          "to": "2025-01-25T08:00:00Z",
          "pct": 60.0,
          "state": "ACTIVE",
          "phase_indices": [2, 3, 4]
        },
        {
          "code": "FLOWERING",
          "name": "Цветение",
          "from": "2025-01-25T08:00:00Z",
          "to": "2025-02-10T08:00:00Z",
          "pct": 0.0,
          "state": "UPCOMING",
          "phase_indices": [5, 6]
        },
        {
          "code": "FRUITING",
          "name": "Плодоношение",
          "from": "2025-02-10T08:00:00Z",
          "to": "2025-02-15T08:00:00Z",
          "pct": 0.0,
          "state": "UPCOMING",
          "phase_indices": [7, 8]
        }
      ]
    }
  }
}
```

**Если активного цикла нет:**

```json
{
  "status": "ok",
  "data": null
}
```

---

### 3. GET /zones/{zone}/snapshot

**Описание:** Получить snapshot состояния зоны (телеметрия, алерты, команды, устройства).

**Query Parameters:**
- `commands_limit` (optional, default: 50, max: 200) — количество последних команд

**Response:**

```json
{
  "status": "ok",
  "data": {
    "snapshot_id": "550e8400-e29b-41d4-a716-446655440000",
    "server_ts": 1705312800000,
    "last_event_id": 12345,
    "zone_id": 5,
    "devices_online_state": [
      {
        "id": 100,
        "uid": "nd-irrig-1",
        "name": "Помпа полива",
        "type": "irrig",
        "status": "online",
        "last_seen_at": "2025-01-15T10:00:00Z",
        "last_heartbeat_at": "2025-01-15T10:00:00Z"
      }
    ],
    "active_alerts": [
      {
        "id": 200,
        "code": "biz_high_temp",
        "type": "TEMP_HIGH",
        "details": {
          "message": "Temperature too high",
          "temp_air": 28.5,
          "target_temp": 25.0
        },
        "status": "ACTIVE",
        "created_at": "2025-01-15T09:00:00Z"
      }
    ],
    "latest_telemetry_per_channel": {
      "default": {
        "100": [
          {
            "metric_type": "PH",
            "value": 6.5,
            "updated_at": "2025-01-15T10:00:00Z"
          },
          {
            "metric_type": "EC",
            "value": 1.8,
            "updated_at": "2025-01-15T10:00:00Z"
          }
        ]
      }
    },
    "commands_recent": [
      {
        "id": 500,
        "cmd_id": "cmd-001",
        "cmd": "set_relay",
        "status": "ack",
        "node_id": 100,
        "channel": "pump_1",
        "params": {"state": true},
        "sent_at": "2025-01-15T09:55:00Z",
        "ack_at": "2025-01-15T09:55:01Z",
        "failed_at": null
      }
    ]
  }
}
```

---

### 4. GET /zones/{zone}/events

**Описание:** Получить события зоны с поддержкой пагинации через `after_id`.

**Query Parameters:**
- `after_id` (optional, integer) — получить события после указанного ID
- `limit` (optional, default: 100, max: 500) — количество событий
- `types` (optional, array) — фильтр по типам событий

**Response:**

```json
{
  "status": "ok",
  "data": {
    "events": [
      {
        "id": 12346,
        "zone_id": 5,
        "type": "CYCLE_PAUSED",
        "entity_type": "grow_cycle",
        "entity_id": "20",
        "payload_json": {
          "cycle_id": 20,
          "user_id": 1,
          "user_name": "Иван Иванов",
          "source": "mobile"
        },
        "created_at": "2025-01-15T10:05:00Z"
      },
      {
        "id": 12345,
        "zone_id": 5,
        "type": "TELEMETRY_UPDATE",
        "entity_type": "telemetry",
        "entity_id": null,
        "payload_json": {
          "metric_type": "PH",
          "value": 6.5,
          "node_id": 100
        },
        "created_at": "2025-01-15T10:00:00Z"
      }
    ],
    "has_more": true,
    "next_after_id": 12340
  }
}
```

**Типы событий, связанных с Grow Cycle:**

- `CYCLE_CREATED` — создан новый цикл
- `CYCLE_STARTED` — цикл запущен
- `CYCLE_PAUSED` — цикл приостановлен
- `CYCLE_RESUMED` — цикл возобновлен
- `CYCLE_HARVESTED` — урожай собран
- `CYCLE_ABORTED` — цикл прерван
- `CYCLE_RECIPE_REBASED` — рецепт цикла изменен
- `STAGE_ADVANCED` — переход на следующую стадию

---

### 5. POST /zones/{zone}/grow-cycles

**Описание:** Создать новый цикл выращивания.

**Request Body:**

```json
{
  "recipe_id": 10,
  "plant_id": 5,
  "planting_at": "2025-01-20T08:00:00Z",
  "settings": {
    "density": 10,
    "substrate": "coco",
    "bush_count": 50
  },
  "start_immediately": true
}
```

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 21,
    "greenhouse_id": 1,
    "zone_id": 5,
    "plant_id": 5,
    "recipe_id": 10,
    "status": "RUNNING",
    "started_at": "2025-01-20T08:00:00Z",
    "recipe_started_at": "2025-01-20T08:00:00Z",
    "expected_harvest_at": "2025-03-05T08:00:00Z",
    "settings": {
      "density": 10,
      "substrate": "coco",
      "bush_count": 50
    },
    "created_at": "2025-01-20T08:00:00Z"
  }
}
```

---

### 6. POST /grow-cycles/{growCycle}/pause

**Описание:** Приостановить цикл.

**Request Body:** Нет

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "status": "PAUSED",
    "updated_at": "2025-01-15T10:05:00Z"
  }
}
```

---

### 7. POST /grow-cycles/{growCycle}/resume

**Описание:** Возобновить цикл.

**Request Body:** Нет

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "status": "RUNNING",
    "updated_at": "2025-01-15T10:10:00Z"
  }
}
```

---

### 8. POST /grow-cycles/{growCycle}/harvest

**Описание:** Завершить цикл (сбор урожая).

**Request Body:**

```json
{
  "batch_label": "Batch-2025-01-15",
  "notes": "Урожай собран успешно"
}
```

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "status": "HARVESTED",
    "actual_harvest_at": "2025-01-15T10:15:00Z",
    "batch_label": "Batch-2025-01-15",
    "notes": "Урожай собран успешно",
    "updated_at": "2025-01-15T10:15:00Z"
  }
}
```

---

### 9. POST /grow-cycles/{growCycle}/abort

**Описание:** Прервать цикл (аварийная остановка).

**Request Body:**

```json
{
  "notes": "Прервано из-за технических проблем"
}
```

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "status": "ABORTED",
    "notes": "Прервано из-за технических проблем",
    "updated_at": "2025-01-15T10:20:00Z"
  }
}
```

---

### 10. POST /zones/{zone}/grow-cycle/change-recipe

**Описание:** Сменить рецепт для активного цикла.

**Request Body:**

```json
{
  "recipe_id": 15,
  "action": "rebase"
}
```

**Параметры:**
- `recipe_id` (required) — ID нового рецепта
- `action` (optional, default: "new_cycle") — "new_cycle" или "rebase"
  - `new_cycle` — создать новый цикл (старый будет прерван)
  - `rebase` — обновить рецепт текущего цикла

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "recipe_id": 15,
    "updated_at": "2025-01-15T10:25:00Z"
  },
  "action": "rebase"
}
```

---

### 11. POST /grow-cycles/{growCycle}/advance-stage

**Описание:** Перейти на следующую стадию цикла.

**Request Body:**

```json
{
  "target_stage_code": "FLOWERING"
}
```

**Параметры:**
- `target_stage_code` (optional) — код целевой стадии. Если не указан, переход на следующую по порядку.

**Response:**

```json
{
  "status": "ok",
  "data": {
    "id": 20,
    "current_stage_code": "FLOWERING",
    "current_stage_started_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

---

## DTO Contracts

### GrowCycleDTO

```typescript
interface GrowCycleDTO {
  id: number;
  greenhouse_id: number;
  zone_id: number;
  plant_id?: number;
  recipe_id?: number;
  zone_recipe_instance_id?: number;
  status: "PLANNED" | "RUNNING" | "PAUSED" | "HARVESTED" | "ABORTED";
  started_at?: string; // ISO 8601
  recipe_started_at?: string; // ISO 8601
  expected_harvest_at?: string; // ISO 8601
  actual_harvest_at?: string; // ISO 8601
  batch_label?: string;
  notes?: string;
  settings?: {
    density?: number;
    substrate?: string;
    bush_count?: number;
    [key: string]: any;
  };
  current_stage_code?: string;
  current_stage_started_at?: string; // ISO 8601
  planting_at?: string; // ISO 8601
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
}
```

### GrowCycleUIDTO (для UI)

```typescript
interface GrowCycleUIDTO {
  cycle: {
    id: number;
    status: "PLANNED" | "RUNNING" | "PAUSED" | "HARVESTED" | "ABORTED";
    planting_at: string; // ISO 8601
    expected_harvest_at?: string; // ISO 8601
    current_stage?: {
      code: string;
      name: string;
      started_at: string; // ISO 8601
    };
    progress: {
      overall_pct: number; // 0-100
      stage_pct: number; // 0-100
    };
    stages: Array<{
      code: string;
      name: string;
      from: string; // ISO 8601
      to?: string; // ISO 8601
      pct: number; // 0-100
      state: "UPCOMING" | "ACTIVE" | "DONE";
      phase_indices: number[];
    }>;
  };
}
```

### SnapshotDTO

```typescript
interface SnapshotDTO {
  snapshot_id: string; // UUID
  server_ts: number; // milliseconds since epoch
  last_event_id: number; // cursor for events sync
  zone_id: number;
  devices_online_state: Array<{
    id: number;
    uid: string;
    name?: string;
    type: string;
    status: "online" | "offline";
    last_seen_at?: string; // ISO 8601
    last_heartbeat_at?: string; // ISO 8601
  }>;
  active_alerts: Array<{
    id: number;
    code: string;
    type: string;
    details: Record<string, any>;
    status: "ACTIVE" | "RESOLVED";
    created_at: string; // ISO 8601
  }>;
  latest_telemetry_per_channel: Record<string, Record<string, Array<{
    metric_type: string;
    value: number;
    updated_at: string; // ISO 8601
  }>>>;
  commands_recent: Array<{
    id: number;
    cmd_id: string;
    cmd: string;
    status: "sent" | "ack" | "failed";
    node_id?: number;
    channel?: string;
    params: Record<string, any>;
    sent_at?: string; // ISO 8601
    ack_at?: string; // ISO 8601
    failed_at?: string; // ISO 8601
    error_code?: string;
    error_message?: string;
    result_code?: string;
    duration_ms?: number;
  }>;
}
```

### EventDTO

```typescript
interface EventDTO {
  id: number;
  zone_id: number;
  type: string;
  entity_type?: string; // "grow_cycle", "telemetry", etc.
  entity_id?: string; // ID сущности (может быть строкой)
  payload_json: Record<string, any>;
  created_at: string; // ISO 8601
}
```

### DashboardZoneDTO

```typescript
interface DashboardZoneDTO {
  id: number;
  name: string;
  status: "online" | "offline" | "warning";
  nodes_total: number;
  nodes_online: number;
  alerts_count: number;
  telemetry: {
    ph?: number;
    ec?: number;
    temperature?: number;
    humidity?: number;
    co2?: number;
  };
  alerts: Array<{
    id: number;
    type: string;
    code: string;
    details: Record<string, any>;
    created_at: string; // ISO 8601
  }>;
  grow_cycle?: {
    id: number;
    status: "PLANNED" | "RUNNING" | "PAUSED" | "HARVESTED" | "ABORTED";
    current_stage?: {
      code: string;
      name: string;
    };
    progress: {
      overall_pct: number;
      stage_pct: number;
    };
    planting_at: string; // ISO 8601
    expected_harvest_at?: string; // ISO 8601
  };
  recipe_instance?: {
    id: number;
    recipe: {
      id: number;
      name: string;
    };
    current_phase_index: number;
  };
}
```

---

## Синхронизация данных

### Стратегия синхронизации

1. **Initial Load:**
   - Получить snapshot: `GET /zones/{zone}/snapshot`
   - Сохранить `last_event_id` из snapshot
   - Получить активный цикл: `GET /zones/{zone}/grow-cycle`

2. **Incremental Sync:**
   - Получить события после `last_event_id`: `GET /zones/{zone}/events?after_id={last_event_id}`
   - Обновить локальное состояние на основе событий
   - Обновить `last_event_id` на максимальный ID из полученных событий

3. **Periodic Refresh:**
   - Периодически (каждые 30-60 секунд) получать новый snapshot
   - Или использовать WebSocket для real-time обновлений

### Пример синхронизации

```kotlin
// 1. Initial load
val snapshot = api.getSnapshot(zoneId)
val lastEventId = snapshot.last_event_id
val growCycle = api.getGrowCycle(zoneId)

// 2. Incremental sync
val events = api.getEvents(zoneId, afterId = lastEventId)
events.forEach { event ->
    when (event.type) {
        "CYCLE_PAUSED" -> updateCycleStatus(event.entity_id, "PAUSED")
        "CYCLE_RESUMED" -> updateCycleStatus(event.entity_id, "RUNNING")
        "STAGE_ADVANCED" -> updateCurrentStage(event.payload_json)
        // ... другие типы событий
    }
}
val newLastEventId = events.maxOf { it.id }
```

---

## События и WebSocket

### WebSocket Events

Приложение может подписаться на WebSocket канал для real-time обновлений:

**Channel:** `zone.{zone_id}`

**События:**

```json
{
  "type": "GrowCycleUpdated",
  "data": {
    "cycle": {
      "id": 20,
      "status": "PAUSED",
      "updated_at": "2025-01-15T10:05:00Z"
    },
    "action": "PAUSED"
  }
}
```

**Типы событий:**

- `GrowCycleUpdated` — обновление цикла (status change, stage advance, etc.)
- `ZoneEvent` — новое событие зоны (telemetry, alerts, commands)

### Обработка событий в приложении

1. При получении `GrowCycleUpdated`:
   - Обновить локальное состояние цикла
   - Обновить UI (статус, прогресс, стадии)

2. При получении `ZoneEvent`:
   - Добавить событие в локальную историю
   - Обновить соответствующие компоненты (телеметрия, алерты)

---

## Обработка ошибок

### Стандартный формат ошибок

```json
{
  "status": "error",
  "message": "Cycle is not running"
}
```

### HTTP Status Codes

- `200 OK` — успешный запрос
- `400 Bad Request` — неверные параметры
- `401 Unauthorized` — требуется аутентификация
- `403 Forbidden` — нет доступа к ресурсу
- `404 Not Found` — ресурс не найден
- `422 Unprocessable Entity` — бизнес-логика не позволяет выполнить операцию
- `500 Internal Server Error` — ошибка сервера

### Типичные ошибки для Grow Cycle

- `"Cycle is not running"` — попытка pause/resume неактивного цикла
- `"Cycle is already completed"` — попытка изменить завершенный цикл
- `"Recipe is required"` — не указан рецепт при создании цикла

---

## Рекомендации по реализации

### 1. Кэширование

- Кэшировать snapshot на клиенте (TTL: 30 секунд)
- Кэшировать активный цикл (обновлять при событиях)
- Использовать `snapshot_id` для проверки актуальности

### 2. Оптимистичные обновления

- При отправке команды (pause/resume) сразу обновить UI
- При получении ошибки — откатить изменения

### 3. Офлайн режим

- Сохранять последний snapshot в локальном хранилище
- При восстановлении соединения — синхронизировать через events

### 4. Валидация данных

- Проверять статус цикла перед действиями
- Валидировать даты (planting_at не в будущем)
- Проверять наличие рецепта перед созданием цикла

---

## Примеры использования

### Создание и запуск цикла

```kotlin
val request = CreateGrowCycleRequest(
    recipeId = 10,
    plantId = 5,
    plantingAt = "2025-01-20T08:00:00Z",
    settings = mapOf(
        "density" to 10,
        "substrate" to "coco"
    ),
    startImmediately = true
)
val cycle = api.createGrowCycle(zoneId, request)
```

### Приостановка цикла

```kotlin
api.pauseGrowCycle(cycleId)
// UI обновляется через WebSocket событие
```

### Получение timeline

```kotlin
val uiData = api.getGrowCycle(zoneId)
val stages = uiData.cycle.stages
val currentStage = uiData.cycle.current_stage
val progress = uiData.cycle.progress
```

---

## Чеклист для разработки

- [ ] Реализовать экран Dashboard Greenhouse
- [ ] Реализовать экран Zone Details с информацией о цикле
- [ ] Реализовать экран Grow Cycle Timeline
- [ ] Интегрировать API endpoints для управления циклом
- [ ] Реализовать синхронизацию через snapshot + events
- [ ] Подключить WebSocket для real-time обновлений
- [ ] Обработать все типы событий цикла
- [ ] Реализовать оптимистичные обновления UI
- [ ] Добавить обработку ошибок
- [ ] Реализовать кэширование данных

---

**Конец документации**

