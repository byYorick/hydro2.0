# API_MAPPING.md
# Маппинг API endpoints: Frontend ↔ Backend

Документ описывает соответствие между используемыми фронтендом API endpoints и их реализацией в backend.
Создан в рамках Волны 1 плана доработки фронтенда.

**Дата создания:** 2025-01-27  
**Статус:** Требует актуализации (проверено 2026-02-11)


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Используемые фронтендом REST API endpoints

### 1.1. Zones (Зоны)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Zones/Show.vue:300` | `/api/zones/{id}/telemetry/history` | GET | `TelemetryController::zoneHistory` | ✅ Используется |
| `Zones/Show.vue:340` | `/api/zones/{id}/commands` | POST | `ZoneCommandController::store` | ✅ Используется |
| `Zones/Tabs/ZoneAutomationTab.vue` | `/api/zones/{id}/grow-cycles` | POST | `GrowCycleController::store` | ✅ Используется |
| `Zones/Tabs/ZoneAutomationTab.vue` | `/api/grow-cycles/{id}/pause` | POST | `GrowCycleController::pause` | ✅ Используется |
| `Zones/Tabs/ZoneAutomationTab.vue` | `/api/grow-cycles/{id}/resume` | POST | `GrowCycleController::resume` | ✅ Используется |
| `Zones/Show.vue:400` | `/api/zones/{id}/commands` | POST | `ZoneCommandController::store` | ✅ Используется |
| `Zones/Tabs/ZoneAutomationTab.vue` | `/api/grow-cycles/{id}/set-phase` | POST | `GrowCycleController::setPhase` | ✅ Используется |
| `Devices/Add.vue:250` | `/api/zones` | GET | `ZoneController::index` | ✅ Используется |
| `Admin/Zones.vue:63` | `/api/zones` | POST | `ZoneController::store` | ✅ Используется |

**Отсутствующие endpoints (требуются для плана):**
- ❌ `/api/zones/{id}/available-actions` - схема допустимых параметров команд (нужен для Волны 2)

### 1.2. Nodes (Узлы)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Devices/Show.vue:114` | `/api/nodes/{id}/commands` | POST | `NodeCommandController::store` | ✅ Используется |
| `Devices/Show.vue:151` | `/api/nodes/{id}/commands` | POST | `NodeCommandController::store` | ✅ Используется |
| `Devices/Show.vue:216` | `/api/commands/{cmdId}/status` | GET | `CommandStatusController::show` | ✅ Используется |
| `Devices/Add.vue:197` | `/api/nodes` | GET | `NodeController::index` | ✅ Используется |
| `Devices/Add.vue:281` | `/api/nodes/{id}` | PATCH | `NodeController::update` | ✅ Используется |

**Отсутствующие endpoints (требуются для плана):**
- ❌ `/api/nodes?search={query}` - поиск узлов для Command Palette (Волна 4)

### 1.3. Recipes (Рецепты)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Recipes/Edit.vue:96` | `/api/recipes/{id}` | PATCH | `RecipeController::update` | ✅ Используется |
| `Admin/Recipes.vue:41` | `/api/recipes/{id}` | PATCH | `RecipeController::update` | ✅ Используется |
| `Recipes/Edit.vue` | `/api/nutrient-products` | GET | `NutrientProductController::index` | ✅ Используется |

**Отсутствующие endpoints (требуются для плана):**
- ❌ `/api/recipes?search={query}` - поиск рецептов для Command Palette (Волна 4)

### 1.4. Alerts (Алерты)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Alerts/Index.vue:86` | `/api/alerts/{id}/ack` | PATCH | `AlertController::ack` | ✅ Используется |

### 1.4.1. Nutrients (Удобрения)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Nutrients/Index.vue` | `/api/nutrient-products` | GET | `NutrientProductController::index` | ✅ Используется |
| `Nutrients/Edit.vue` | `/api/nutrient-products` | POST | `NutrientProductController::store` | ✅ Используется |
| `Nutrients/Edit.vue` | `/api/nutrient-products/{id}` | PATCH | `NutrientProductController::update` | ✅ Используется |
| `Nutrients/Edit.vue` | `/api/nutrient-products/{id}` | DELETE | `NutrientProductController::destroy` | ✅ Используется |

### 1.5. Greenhouses (Теплицы)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Devices/Add.vue:231` | `/api/greenhouses` | GET | `GreenhouseController::index` | ✅ Используется |
| `Admin/Zones.vue:52` | `/api/greenhouses` | GET | `GreenhouseController::index` | ✅ Используется |

### 1.6. Telemetry (Телеметрия)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Zones/Show.vue:300` | `/api/zones/{id}/telemetry/history` | GET | `TelemetryController::zoneHistory` | ✅ Используется |

**Отсутствующие endpoints (требуются для плана):**
- ❌ `/api/telemetry/aggregates` - агрегированные данные для мини-графиков Dashboard (Волна 3)

### 1.7. Commands (Команды)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `Zones/Show.vue:340,400` | `/api/zones/{id}/commands` | POST | `ZoneCommandController::store` | ✅ Используется |
| `Devices/Show.vue:114,151` | `/api/nodes/{id}/commands` | POST | `NodeCommandController::store` | ✅ Используется |
| `Devices/Show.vue:216` | `/api/commands/{cmdId}/status` | GET | `CommandStatusController::show` | ✅ Используется |

### 1.8. Simulations (Симуляции)

| Frontend использование | Backend endpoint | Метод | Контроллер | Статус |
|------------------------|------------------|-------|------------|--------|
| `ZoneSimulationModal.vue:256` | `/api/zones/{id}/simulate` | POST | `SimulationController::simulateZone` | ✅ Используется |

---

## 2. Inertia Props (данные, передаваемые через web.php)

### 2.1. Dashboard (`/`)

**Route:** `routes/web.php:13-92`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'dashboard' => [
        'greenhousesCount' => int,
        'zonesCount' => int,
        'devicesCount' => int,
        'alertsCount' => int,
        'zonesByStatus' => ['RUNNING' => int, 'PAUSED' => int, ...],
        'nodesByStatus' => ['online' => int, 'offline' => int, ...],
        'problematicZones' => [...],
        'greenhouses' => [...],
        'latestAlerts' => [...],
    ]
]
```

**Источник данных:** Прямые запросы к БД через Eloquent, кеширование 30 сек

---

### 2.2. Zones Index (`/zones`)

**Route:** `routes/web.php:95-138`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'zones' => [
        // Каждая зона содержит:
        'id' => int,
        'name' => string,
        'status' => 'RUNNING|PAUSED|WARNING|ALARM',
        'description' => string,
        'greenhouse_id' => int,
        'greenhouse' => ['id' => int, 'name' => string],
        'telemetry' => [
            'ph' => float|null,
            'ec' => float|null,
            'temperature' => float|null,
            'humidity' => float|null,
        ]
    ]
]
```

**Источник данных:** 
- Zones: `Zone::query()` с кешированием 10 сек
- Telemetry: `TelemetryLast::query()` batch loading для всех зон

---

### 2.3. Zone Show (`/zones/{zoneId}`)

**Route:** `routes/web.php:139-286`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'zoneId' => int,
    'zone' => [
        'id' => int,
        'name' => string,
        'status' => 'RUNNING|PAUSED|WARNING|ALARM',
        'description' => string,
        'greenhouse_id' => int,
        'greenhouse' => ['id' => int, 'name' => string],
        'recipeInstance' => [
            'recipe' => ['id' => int, 'name' => string],
            'current_phase_index' => int,
        ]
    ],
    'telemetry' => [
        'ph' => float|null,
        'ec' => float|null,
        'temperature' => float|null,
        'humidity' => float|null,
    ],
    'targets' => [
        // Цели из текущей фазы рецепта
        'ph_min' => float,
        'ph_max' => float,
        'ec_min' => float,
        'ec_max' => float,
        // ... другие параметры
    ],
    'devices' => [
        // Список устройств зоны
        'id' => int,
        'uid' => string,
        'zone_id' => int,
        'name' => string,
        'type' => string,
        'status' => string,
        'fw_version' => string,
        'last_seen_at' => datetime,
        'zone' => ['id' => int, 'name' => string],
    ],
    'events' => [
        // Последние 20 событий зоны
        'id' => int,
        'kind' => 'ALERT|WARNING|INFO',
        'message' => string,
        'occurred_at' => ISO8601 string,
    ],
    'cycles' => [
        'PH_CONTROL' => [
            'type' => 'PH_CONTROL',
            'strategy' => 'periodic|on_demand',
            'interval' => int (секунды),
            'last_run' => ISO8601 string|null,
            'next_run' => ISO8601 string|null,
        ],
        'EC_CONTROL' => [...],
        'IRRIGATION' => [...],
        'LIGHTING' => [...],
        'CLIMATE' => [...],
    ]
]
```

**Источник данных:**
- Zone: `Zone::query()` с relations
- Telemetry: `TelemetryLast::query()`
- Targets: из `recipeInstance.recipe.phases` (текущая фаза)
- Devices: `DeviceNode::query()` для зоны
- Events: `Event::query()` (если модель существует)
- Cycles: вычисляется из `zone.settings` и последних команд

---

### 2.4. Devices Index (`/devices`)

**Route:** `routes/web.php:289-325`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'devices' => [
        'id' => int,
        'uid' => string,
        'zone_id' => int,
        'name' => string,
        'type' => string,
        'status' => string,
        'fw_version' => string,
        'last_seen_at' => datetime,
        'zone' => ['id' => int, 'name' => string],
    ]
]
```

**Источник данных:** `DeviceNode::query()` с кешированием 10 сек

---

### 2.5. Recipes Index (`/recipes`)

**Route:** `routes/web.php:327-368`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'recipes' => [
        'id' => int,
        'name' => string,
        'description' => string,
        'phases_count' => int,
    ]
]
```

**Источник данных:** `Recipe::query()` с `withCount('phases')`, кеширование 10 сек

---

### 2.6. Alerts Index (`/alerts`)

**Route:** `routes/web.php:370-386`

**Inertia Props:**
```php
[
    'auth' => ['user' => ['role' => 'viewer|operator|admin|agronomist|engineer']],
    'alerts' => [
        'id' => int,
        'type' => string,
        'status' => 'active|resolved',
        'details' => array,
        'zone_id' => int,
        'created_at' => datetime,
        'resolved_at' => datetime|null,
        'zone' => ['id' => int, 'name' => string],
    ]
]
```

**Источник данных:** `Alert::query()` с кешированием 5 сек

---

## 3. WebSocket каналы (Laravel Broadcasting)

### 3.1. Команды зон

**Канал:** `commands.{zoneId}`  
**Использование:** Волна 2 - отображение статуса команд  
**Статус:** ❌ Требуется настройка Laravel Echo на фронтенде

**Формат сообщений:**
```json
{
    "command_id": int,
    "status": "pending|executing|completed|failed",
    "zone_id": int,
    "message": string,
    "error": string|null
}
```

### 3.2. Глобальные события

**Канал:** `events.global`  
**Использование:** Волна 3 - обновление событий в Dashboard  
**Статус:** ❌ Требуется настройка Laravel Echo на фронтенде

**Формат сообщений:**
```json
{
    "id": int,
    "kind": "ALERT|WARNING|INFO",
    "message": string,
    "zone_id": int|null,
    "occurred_at": "ISO8601 string"
}
```

---

## 4. Отсутствующие endpoints (требуются для плана)

### 4.1. Волна 2

- ❌ `GET /api/zones/{id}/available-actions` - схема допустимых параметров для команд зоны
  - **Назначение:** Получить список доступных действий и их параметров для зоны
  - **Формат ответа:**
  ```json
  {
      "status": "ok",
      "data": {
          "FORCE_IRRIGATION": {
              "params": {
                  "duration_sec": {"type": "integer", "min": 1, "max": 3600, "default": 10}
              }
          },
          "FORCE_PH_CONTROL": {
              "params": {
                  "target_ph": {"type": "float", "min": 4.0, "max": 9.0}
              }
          }
      }
  }
  ```

### 4.2. Волна 3

- ❌ `GET /api/telemetry/aggregates` - агрегированные данные телеметрии
  - **Назначение:** Получить агрегированные данные для мини-графиков Dashboard
  - **Параметры:** `zone_id`, `metric` (ph|ec|temp|humidity), `period` (24h|7d|30d)
  - **Формат ответа:**
  ```json
  {
      "status": "ok",
      "data": [
          {"ts": "ISO8601", "value": float, "min": float, "max": float, "avg": float}
      ]
  }
  ```

### 4.3. Волна 4

- ❌ `GET /api/zones?search={query}` - поиск зон для Command Palette
  - **Назначение:** Поиск зон по имени/описанию
  - **Параметры:** `search` (string), `limit` (int, default: 10)
  
- ❌ `GET /api/nodes?search={query}` - поиск узлов для Command Palette
  - **Назначение:** Поиск узлов по UID/имени
  - **Параметры:** `search` (string), `limit` (int, default: 10)
  
- ❌ `GET /api/recipes?search={query}` - поиск рецептов для Command Palette
  - **Назначение:** Поиск рецептов по имени/описанию
  - **Параметры:** `search` (string), `limit` (int, default: 10)
  
- ❌ `GET /api/actions/available` - список доступных быстрых действий
  - **Назначение:** Получить список действий для Command Palette
  - **Формат ответа:**
  ```json
  {
      "status": "ok",
      "data": [
          {
              "id": "zone_pause",
              "label": "Поставить зону на паузу",
              "endpoint": "/api/grow-cycles/{id}/pause",
              "requires_confirmation": true
          }
      ]
  }
  ```

---

## 5. Соответствие REST_API_REFERENCE.md

### 5.1. Полное соответствие ✅

Все используемые фронтендом endpoints присутствуют в `../04_BACKEND_CORE/REST_API_REFERENCE.md`:
- Zones endpoints ✅
- Nodes endpoints ✅
- Recipes endpoints ✅
- Alerts endpoints ✅
- Telemetry endpoints ✅
- Commands endpoints ✅

### 5.2. Дополнительные endpoints в api.php

В `routes/api.php` есть endpoints, которые не используются фронтендом, но описаны в `../04_BACKEND_CORE/REST_API_REFERENCE.md`:
- AI endpoints (`/api/ai/*`)
- Simulations endpoints (`/api/simulations/*`)
- Reports endpoints (`/api/recipes/{id}/analytics`, etc.)
- Presets endpoints (`/api/presets/*`)

---

## 6. Рекомендации

### 6.1. Немедленные действия (Волна 1)

1. ✅ Создан файл `API_MAPPING.md` (этот документ)
2. ⏳ Добавить комментарии в `routes/web.php` с описанием всех Inertia props
3. ⏳ Проверить соответствие всех endpoints с `../04_BACKEND_CORE/REST_API_REFERENCE.md`

### 6.2. Для Волны 2

1. Создать endpoint `GET /api/zones/{id}/available-actions`
2. Настроить Laravel Echo для канала `commands.{zoneId}`

### 6.3. Для Волны 3

1. Создать endpoint `GET /api/telemetry/aggregates`
2. Настроить Laravel Echo для канала `events.global`

### 6.4. Для Волны 4

1. Добавить параметр `search` в существующие endpoints:
   - `GET /api/zones?search={query}`
   - `GET /api/nodes?search={query}`
   - `GET /api/recipes?search={query}`
2. Создать endpoint `GET /api/actions/available`

---

**Дата последнего обновления:** 2025-01-27  
**Версия:** 1.0
