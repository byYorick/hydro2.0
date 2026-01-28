# API_SPEC_FRONTEND_BACKEND_FULL.md
# Полная детальная спецификация API между Frontend и Backend (2.0)
# **ОБНОВЛЕНО ПОСЛЕ МЕГА-РЕФАКТОРИНГА 2025-12-25**

Документ описывает REST и WebSocket-API, которые использует frontend (Web/Android)
для работы с системой 2.0.

**КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ПОСЛЕ РЕФАКТОРИНГА:**
- ✅ Новые эндпоинты для GrowCycle: `/api/grow-cycles/*`
- ✅ Удалены legacy эндпоинты: `/api/zones/*/attach-recipe`
- ✅ Новый internal API: `/api/internal/effective-targets/batch`
- ✅ Версионирование рецептов: `/api/recipe-revisions/*`

Задача документа:
- зафиксировать **контракты**;
- помочь ИИ-агентам не плодить несогласованные эндпоинты;
- обеспечить обратную совместимость при эволюции API.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общие принципы API

- Базовый префикс REST-API: `/api`.
- Все ответы — JSON.
- Аутентификация — token-based (например, `Authorization: Bearer <token>`).
- Валидация на backend → фронт получает структурированные ошибки.
- Локализация сообщений об ошибках — через стандартные механизмы Laravel.

### 1.1. Требования аутентификации

**Публичные эндпоинты** (не требуют аутентификации):
- `GET /api/system/health` - проверка здоровья сервиса
- `GET /api/system/config/full` - полная конфигурация (для Python сервисов)
- `POST /api/python/ingest/telemetry` - инжест телеметрии (token-based)
- `POST /api/python/commands/ack` - подтверждение команд (token-based)
- `POST /api/alerts/webhook` - webhook от Alertmanager

**Защищенные эндпоинты** (требуют `auth:sanctum`):
- Все эндпоинты в разделах 3-7, 9-12 требуют аутентификации через Laravel Sanctum
- Раздел 2 (Auth): `POST /api/auth/logout` и `GET /api/auth/me` требуют аутентификации
- Раздел 8 (System): полностью публичный (для Python сервисов)
- Токен передается в заголовке: `Authorization: Bearer <token>`
- Токен получается через `POST /api/auth/login`

**Роли и права доступа**:
- `viewer` - только чтение данных
- `operator` - чтение + управление зонами, подтверждение алертов
- `admin` - полный доступ, включая управление пользователями

Стандартный формат ответа:

```json
{
 "status": "ok",
 "data": { }
}
```

Формат ошибок:

```json
{
 "status": "error",
 "message": "Invalid request",
 "code": 400,
 "errors": {
 "field": ["Error description"]
 }
}
```

---

## 2. Auth API

**Аутентификация:** Смешанная - `login` публичный, остальные требуют `auth:sanctum`.

### 2.1. POST /api/auth/login

- **Аутентификация:** Не требуется (публичный эндпоинт)
- Вход: `{ "email": " ", "password": " " }`
- Выход (успех):

```json
{
 "status": "ok",
 "data": {
 "token": " ",
 "user": {
 "id": 1,
 "name": "Operator",
 "roles": ["admin"]
 }
 }
}
```

### 2.2. POST /api/auth/logout

- **Аутентификация:** Требуется `auth:sanctum`
- Выход: `{"status": "ok"}`

### 2.3. GET /api/auth/me

- **Аутентификация:** Требуется `auth:sanctum`
- Возвращает текущего пользователя и его права.

---

## 3. Grow Cycles API (НОВОЕ после рефакторинга)

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`, роль `agronomist`.

**Центр API для управления циклами выращивания.**

### 3.1. GET /api/zones/{zone}/grow-cycle

- **Описание:** Получить активный цикл зоны с effective targets
- **Аутентификация:** Требуется `auth:sanctum`
- **Ответ:**
```json
{
  "status": "ok",
  "data": {
    "id": 123,
    "zone_id": 5,
    "plant": {"id": 1, "name": "Tomato"},
    "recipe_revision": {
      "id": 456,
      "recipe": {"name": "Standard Tomato"},
      "version": 2
    },
    "current_phase": {
      "id": 789,
      "name": "VEG",
      "started_at": "2025-01-01T10:00:00Z",
      "progress": 0.3
    },
    "status": "RUNNING",
    "effective_targets": {
      "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
      "ec": {"target": 1.5, "min": 1.3, "max": 1.7}
      // ... остальные цели
    }
  }
}
```

### 3.2. POST /api/zones/{zone}/grow-cycles

- **Описание:** Создать новый цикл выращивания
- **Тело запроса:**
```json
{
  "recipe_revision_id": 456,
  "plant_id": 1,
  "planting_at": "2025-01-01T08:00:00Z",
  "batch_label": "Batch 2025-001",
  "notes": "Test cycle"
}
```

### 3.3. POST /api/grow-cycles/{id}/pause

- **Описание:** Приостановить цикл

### 3.4. POST /api/grow-cycles/{id}/resume

- **Описание:** Возобновить цикл

### 3.5. POST /api/grow-cycles/{id}/set-phase

- **Описание:** Ручной переход на фазу
- **Тело:** `{"phase_index": 1, "comment": "Early transition due to plant health"}`

### 3.6. POST /api/grow-cycles/{id}/advance-phase

- **Описание:** Перейти на следующую фазу

### 3.7. POST /api/grow-cycles/{id}/change-recipe-revision

- **Описание:** Сменить ревизию рецепта
- **Тело:** `{"recipe_revision_id": 789, "apply_at_next_phase": true}`

### 3.8. POST /api/grow-cycles/{id}/harvest

- **Описание:** Завершить цикл сбором урожая
- **Тело:** `{"actual_harvest_at": "2025-02-01T12:00:00Z", "yield_kg": 15.5}`

---

## 4. Recipe Revisions API (НОВОЕ)

**Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`.

### 4.1. GET /api/recipes/{recipe}/revisions

- **Описание:** Список ревизий рецепта

### 4.2. POST /api/recipes/{recipe}/revisions

- **Описание:** Создать новую ревизию из существующей
- **Тело:** `{"from_revision_id": 456, "description": "Optimized for summer conditions"}`

### 4.3. PATCH /api/recipe-revisions/{id}

- **Описание:** Редактировать DRAFT ревизию

### 4.4. POST /api/recipe-revisions/{id}/publish

- **Описание:** Опубликовать DRAFT ревизию

### 4.5. GET /api/recipe-revisions/{id}

- **Описание:** Получить ревизию с фазами

---

## 5. Internal API (для Python сервисов)

**Аутентификация:** Token-based (LARAVEL_API_TOKEN)

### 5.1. POST /api/internal/effective-targets/batch

- **Описание:** Batch получение effective targets для зон
- **Тело:** `{"zone_ids": [1, 2, 3]}`
- **Ответ:** Массив effective targets по зонам

### 5.2. POST /api/internal/realtime/telemetry-batch

- **Описание:** Batched realtime ingest телеметрии для WebSocket
- **Тело:**
```json
{
  "updates": [
    {
      "zone_id": 1,
      "node_id": 10,
      "channel": "ph_sensor",
      "metric_type": "PH",
      "value": 6.2,
      "timestamp": 1700000000000
    }
  ]
}
```
- **Ограничения:** `REALTIME_BATCH_MAX_UPDATES`, `REALTIME_BATCH_MAX_BYTES`
- **Ответ:** `{"status":"ok","broadcasted":1,"updates":1}`

---

## 6. Greenhouses / Zones / Nodes (ОБНОВЛЕНО)

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 3.1. GET /api/greenhouses

- **Аутентификация:** Требуется `auth:sanctum`
- Список теплиц с краткой информацией.

### 3.2. POST /api/greenhouses

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin` или `operator`
- Создание теплицы.

### 3.3. GET /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация + связанные зоны.

### 3.3.1. PATCH /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin` или `operator`
- Обновление теплицы.

### 3.3.2. DELETE /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление теплицы (если безопасно, нет связанных зон).

### 3.4. GET /api/zones

- **Аутентификация:** Требуется `auth:sanctum`
- Список зон (с фильтрами по теплице, статусу и т.п.).

### 3.5. GET /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Полная карточка зоны:
 - конфигурация;
 - активный рецепт и фаза;
 - привязанные узлы и каналы;
 - последние значения ключевых метрик.

### 3.6. POST /api/zones

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Создание зоны.

### 3.7. PATCH /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Обновление параметров зоны (название, тип, лимиты и т.п.).

### 3.7.1. DELETE /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление зоны (если нет активных зависимостей).

### 3.8. GET /api/nodes

- **Аутентификация:** Требуется `auth:sanctum`
- Список узлов ESP32, их статус (online/offline), привязка к зонам.

### 3.9. GET /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация об узле:
 - NodeConfig;
 - список каналов;
 - последняя телеметрия.

### 3.9.1. POST /api/nodes

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Регистрация нового узла ESP32.

### 3.9.2. PATCH /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Обновление метаданных узла (name, zone_id).

### 3.9.3. DELETE /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление узла.

### 3.9.4. GET /api/nodes/{id}/config

- **Аутентификация:** Требуется `auth:sanctum`
- Получение сохраненного NodeConfig (read-only), полученного от ноды через `config_report`.

Ответ:
```json
{
 "status": "ok",
 "data": {
   "node_uid": "nd-001",
   "zone_id": 1,
   "channels": [...],
   "settings": {...}
 }
}
```

### 3.9.5. POST /api/nodes/{id}/config/publish

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Публикация конфигурации узла через MQTT **отключена**.
- Узлы отправляют конфиг самостоятельно (config_report), сервер хранит и использует его.

Ответ:
```json
{
 "status": "error",
 "message": "Config publishing from server is disabled. Nodes send config_report on connect."
}
```

### 3.9.6. POST /api/nodes/{id}/swap

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Замена узла новым узлом с миграцией данных.

Тело запроса:
```json
{
 "new_hardware_id": "ESP32-ABC123",
 "migrate_telemetry": true,
 "migrate_channels": true
}
```

Ответ:
```json
{
 "status": "ok",
 "data": {
   "old_node_id": 1,
   "new_node_id": 2,
   "migrated_telemetry_count": 1000,
   "migrated_channels_count": 4
 }
}
```

---

## 4. Recipes API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 4.1. GET /api/recipes

- **Аутентификация:** Требуется `auth:sanctum`
- Список рецептов (фильтры по типу культур, активности).

### 4.2. POST /api/recipes

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Создание рецепта и базового набора фаз.

### 4.3. GET /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальное описание рецепта + фазы.

### 4.4. PATCH /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Обновление рецепта (описание, культура и т.п.).

### 4.4.1. DELETE /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление рецепта.

### 4.5. POST /api/recipes/{id}/phases

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Добавление фазы к рецепту.

### 4.6. PATCH /api/recipe-phases/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Обновление параметров фазы (цели pH, EC, продолжительность и т.п.).

### 4.6.1. DELETE /api/recipe-phases/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление фазы рецепта.

### 4.7. POST /api/zones/{id}/attach-recipe

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Назначение рецепта на зону.
- Тело:

```json
{
 "recipe_id": 1,
 "start_at": "2025-11-15T10:00:00Z"
}
```

### 4.8. POST /api/zones/{id}/change-phase

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Ручной переход зоны на другую фазу.

### 4.9. POST /api/zones/{id}/pause

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Приостановка работы зоны (временная остановка автоматизации).

### 4.10. POST /api/zones/{id}/resume

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Возобновление работы зоны после паузы.

### 4.11. GET /api/zones/{id}/cycles

- **Аутентификация:** Требуется `auth:sanctum`
- Получение информации о циклах зоны (PH_CONTROL, EC_CONTROL, IRRIGATION, LIGHTING, CLIMATE).

Ответ:
```json
{
 "status": "ok",
 "data": {
   "PH_CONTROL": {
     "type": "PH_CONTROL",
     "strategy": "periodic",
     "interval": 300,
     "last_run": "2025-11-17T10:00:00Z",
     "next_run": "2025-11-17T10:05:00Z"
   },
   "EC_CONTROL": {
     "type": "EC_CONTROL",
     "strategy": "periodic",
     "interval": 300,
     "last_run": null,
     "next_run": null
   },
   "IRRIGATION": {
     "type": "IRRIGATION",
     "strategy": "periodic",
     "interval": 3600,
     "last_run": "2025-11-17T09:00:00Z",
     "next_run": "2025-11-17T10:00:00Z"
   },
   "LIGHTING": {
     "type": "LIGHTING",
     "strategy": "periodic",
     "interval": 43200,
     "last_run": null,
     "next_run": null
   },
   "CLIMATE": {
     "type": "CLIMATE",
     "strategy": "periodic",
     "interval": 300,
     "last_run": "2025-11-17T09:55:00Z",
     "next_run": "2025-11-17T10:00:00Z"
   }
 }
}
```

---

## 5. Telemetry & History API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 5.1. GET /api/zones/{id}/telemetry/last

- **Аутентификация:** Требуется `auth:sanctum`
- Последние значения ключевых метрик по зоне.

### 5.2. GET /api/zones/{id}/telemetry/history

- **Аутентификация:** Требуется `auth:sanctum`
- Параметры:
  - `metric` — например, `PH`, `EC`, `TEMPERATURE`;
  - `from`, `to` — временной диапазон.
- Ответ — массив точек для графика.

### 5.3. GET /api/nodes/{id}/telemetry/last

- **Аутентификация:** Требуется `auth:sanctum`
- Последняя телеметрия по канальным метрикам узла.

---

## 6. Commands API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`, роль `operator` или `admin`.

### 6.1. POST /api/zones/{id}/commands

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- **Валидация:** Используется `StoreZoneCommandRequest` для валидации входных данных
- **Авторизация:** Проверка прав через `ZonePolicy::sendCommand`
- **HMAC подпись:** Команды автоматически подписываются HMAC с timestamp перед отправкой в Python-сервис
- Отправка команд на зону (через Python-сервис).
- Примеры команд:
 - `FORCE_IRRIGATION` - принудительный полив (требует `params.duration_sec`);
 - `FORCE_DRAIN` - принудительный дренаж;
 - `FORCE_PH_CONTROL` - принудительный контроль pH;
 - `FORCE_EC_CONTROL` - принудительный контроль EC;
 - `FORCE_LIGHTING` - принудительное управление освещением;
 - `FORCE_CLIMATE` - принудительное управление климатом;
 - `FORCE_LIGHT_ON/OFF` - включение/выключение света (устаревшая, используйте `FORCE_LIGHTING`);
 - `ZONE_PAUSE/RESUME` - приостановка/возобновление зоны (лучше использовать `/api/zones/{id}/pause` и `/api/zones/{id}/resume`).

Тело запроса:

```json
{
 "type": "FORCE_IRRIGATION",
 "params": {
 "duration_sec": 30
 }
}
```

Ответ:

```json
{
 "status": "ok",
 "data": {
 "command_id": "cmd- "
 }
}
```

### 6.2. POST /api/nodes/{id}/commands

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- **Валидация:** Используется `StoreNodeCommandRequest` для валидации входных данных
- **Авторизация:** Проверка прав через `DeviceNodePolicy::sendCommand`
- **HMAC подпись:** Команды автоматически подписываются HMAC с timestamp перед отправкой в Python-сервис
- Низкоуровневые команды для конкретного узла (диагностика, калибровка).

---

## 7. Alerts & Events API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 7.1. GET /api/alerts

- **Аутентификация:** Требуется `auth:sanctum`
- Список активных/исторических алертов.

### 7.2. GET /api/alerts/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация об алерте.

### 7.3. PATCH /api/alerts/{id}/ack

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Подтверждение алерта оператором.

### 7.4. GET /api/alerts/stream

- **Аутентификация:** Требуется `auth:sanctum`
- Server-Sent Events поток алертов для realtime обновлений.

---

## 8. System API

### 8.1. GET /api/system/config/full

- **Аутентификация:** Публичный эндпоинт (для Python сервисов)
- Полная конфигурация теплиц/зон/узлов/каналов для Python/AI.

### 8.2. GET /api/system/health

- **Аутентификация:** Публичный эндпоинт
- Проверка здоровья сервиса.

---

## 9. Presets API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 9.1. GET /api/presets

- Список пресетов (шаблонов конфигураций).

### 9.2. POST /api/presets

- Создание нового пресета.

### 9.3. GET /api/presets/{id}

- Детальная информация о пресете.

### 9.4. PATCH /api/presets/{id}

- Обновление пресета.

### 9.5. DELETE /api/presets/{id}

- Удаление пресета.

---

## 10. Reports & Analytics API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 10.1. GET /api/recipes/{id}/analytics

- Аналитика по рецепту (статистика, эффективность, урожайность).

### 10.2. GET /api/zones/{id}/harvests

- История урожаев по зоне.

### 10.3. POST /api/harvests

- Регистрация нового урожая.

Тело запроса:
```json
{
  "zone_id": 1,
  "crop": "Tomato",
  "weight_kg": 15.5,
  "harvested_at": "2025-01-15T10:00:00Z",
  "notes": "First harvest of the season"
}
```

### 10.4. POST /api/recipes/comparison

- Сравнение нескольких рецептов по метрикам.

---

## 11. AI API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 11.1. POST /api/ai/predict

- Прогнозирование параметров для зоны.

Тело запроса:
```json
{
  "zone_id": 1,
  "metric_type": "PH",
  "horizon_minutes": 60
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "predicted_value": 6.2,
    "confidence": 0.85,
    "predicted_at": "2025-01-15T11:00:00Z",
    "horizon_minutes": 60
  }
}
```

### 11.2. POST /api/ai/explain_zone

- Объяснение текущего состояния зоны (AI анализ).

### 11.3. POST /api/ai/recommend

- Получение рекомендаций AI по оптимизации зоны.

### 11.4. POST /api/ai/diagnostics

- Запуск диагностики системы (анализ телеметрии, событий, выявление проблем).

---

## 12. Simulations API (Digital Twin)

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 12.1. POST /api/simulations/zone/{zone}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin`
- Запуск симуляции Digital Twin для зоны.
  - `full_simulation` (bool, optional) — выполнить полный цикл с созданием сущностей и отчетом.

Тело запроса:
```json
{
  "scenario": "optimize_ph",
  "duration_hours": 24,
  "parameters": {
    "target_ph": 6.5
  },
  "full_simulation": false
}
```

### 12.2. GET /api/simulations/{job_id}

- **Аутентификация:** Требуется `auth:sanctum`
- Получение статуса симуляции (job), прогресса и отчета.

Ответ:
```json
{
  "status": "ok",
  "data": {
    "status": "processing",
    "simulation_id": 55,
    "report": {
      "id": 12,
      "simulation_id": 55,
      "zone_id": 12,
      "status": "completed",
      "started_at": "2026-01-26T09:10:00Z",
      "finished_at": "2026-01-26T09:11:00Z",
      "summary_json": { "simulation_zone_id": 99 },
      "phases_json": [],
      "metrics_json": { "phases_count": 3 },
      "errors_json": null
    }
  }
}
```

### 12.3. GET /api/simulations/{simulation}/events

- **Аутентификация:** Требуется `auth:sanctum`
- Возвращает события процесса симуляции (этапы, статусы, ошибки).

Параметры запроса (query):
```
limit (1..200, default 100)
order (asc|desc, default asc)
service (string)
stage (string)
status (string)
level (info|warning|error)
after_id (int)
since (ISO8601 date/time)
```

Ответ:
```json
{
  "status": "ok",
  "data": [
    {
      "id": 101,
      "simulation_id": 55,
      "zone_id": 12,
      "service": "digital-twin",
      "stage": "live_start",
      "status": "completed",
      "level": "info",
      "message": "Live-симуляция запущена",
      "payload": { "node_sim_session_id": "sim-12-1700000000" },
      "occurred_at": "2026-01-26T09:10:00Z",
      "created_at": "2026-01-26T09:10:00Z"
    }
  ],
  "meta": {
    "limit": 100,
    "order": "asc",
    "last_id": 101
  }
}
```

### 12.4. GET /api/simulations/{simulation}/events/stream

- **Аутентификация:** Требуется `auth:sanctum`
- SSE-стрим новых событий симуляции.

Параметры запроса (query):
```
last_id (int)
service (string)
stage (string)
status (string)
level (info|warning|error)
```

События приходят с именем `simulation_event`.

---

## 13. WebSocket / Realtime

Для realtime-обновлений используется **Laravel Reverb** (встроенный WebSocket сервер).

**Подключение:**
- WebSocket endpoint: `ws://localhost:6001` (или `wss://` для HTTPS)
- Используется библиотека `laravel-echo` и `pusher-js` на клиенте
- Аутентификация через тот же токен, что и REST API

**Основные каналы:**

- `hydro.zones.{id}` — обновления по зоне (`ZoneUpdated`, `NodeConfigUpdated`, `TelemetryBatchUpdated`);
- `hydro.alerts` — новые алерты (событие `AlertCreated`);
- `hydro.devices` — обновления устройств без зоны (fallback для `NodeConfigUpdated`).

**Формат событий:**
```json
{
  "event_type": "zone_state_updated",
  "event_id": "uuid-123",
  "occurred_at": "2025-01-15T12:00:00Z",
  "payload": {
    "zone_id": 1,
    "metrics": { "ph": 6.2, "ec": 1.8 }
  }
}
```

Подробнее см. `REALTIME_UPDATES_ARCH.md`.

---

## 13. Node Registration API

**Аутентификация:** Токен-базированная (service token), не требует `auth:sanctum`.

### 13.1. POST /api/nodes/register

- **Аутентификация:** Требуется service token (Bearer token) или IP whitelist
- **Rate Limiting:** Максимум 10 запросов в минуту по IP
- **IP Whitelist:** Настраивается через `services.node_registration.allowed_ips` (поддержка CIDR)
- **Валидация:** Используется `RegisterNodeRequest` для валидации входных данных
- Регистрация нового узла ESP32 в системе.

**Безопасность:**
- Обязательная проверка токена (если настроен)
- Rate limiting по IP (10 запросов/минуту)
- IP whitelist (если настроен)
- Защита от дублирования через уникальные ограничения в БД

Тело запроса (node_hello):
```json
{
  "message_type": "node_hello",
  "hardware_id": "ESP32-ABC123",
  "node_type": "ph",
  "fw_version": "2.0.1",
  "hardware_revision": "v1.0",
  "capabilities": {...},
  "provisioning_meta": {...}
}
```

Тело запроса (обычная регистрация):
```json
{
  "node_uid": "nd-001",
  "firmware_version": "2.0.1",
  "hardware_revision": "v1.0",
  "hardware_id": "ESP32-ABC123",
  "name": "pH Sensor Node",
  "type": "ph"
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "uid": "nd-001",
    "name": "pH Sensor Node",
    "type": "ph",
    "status": "offline",
    "lifecycle_state": "REGISTERED_BACKEND"
  }
}
```

---

## 14. Правила для ИИ-агентов

1. Все новые эндпоинты должны описываться здесь и в `REST_API_REFERENCE.md`.
2. Нельзя менять сигнатуру существующих эндпоинтов без явного указания версии (например, `/api/v2/`).
3. Все действия, влияющие на железо, должны проходить через Python-сервис (не ходить напрямую в MQTT из backend).
4. При добавлении нового эндпоинта обязательно указать требования аутентификации.
5. Публичные эндпоинты должны быть явно помечены как таковые.
6. Все мутирующие операции должны использовать FormRequest для валидации и Policy для авторизации.
7. Критичные операции (публикация конфигов, регистрация узлов) должны использовать блокировки и дедупликацию.

Этот документ задаёт **единый контракт** между UI и backend и служит опорой для дальнейшего развития системы.
