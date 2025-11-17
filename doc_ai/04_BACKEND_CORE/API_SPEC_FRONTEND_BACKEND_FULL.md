# API_SPEC_FRONTEND_BACKEND_FULL.md
# Полная детальная спецификация API между Frontend и Backend (2.0)

Документ описывает REST и WebSocket-API, которые использует frontend (Web/Android)
для работы с системой 2.0.

Задача документа:
- зафиксировать **контракты**;
- помочь ИИ-агентам не плодить несогласованные эндпоинты;
- обеспечить обратную совместимость при эволюции API.

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

## 3. Greenhouses / Zones / Nodes

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
- Обновление конфигурации узла.

### 3.9.3. DELETE /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление узла.

### 3.9.4. GET /api/nodes/{id}/config

- **Аутентификация:** Требуется `auth:sanctum`
- Получение конфигурации узла (NodeConfig) для отправки на ESP32.

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
- Публикация конфигурации узла через MQTT для отправки на ESP32.

Ответ:
```json
{
 "status": "ok",
 "data": {
   "published_at": "2025-11-17T10:00:00Z",
   "topic": "hydro/nodes/nd-001/config"
 }
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
  - `metric` — например, `PH`, `EC`, `TEMP_AIR`;
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
  "metric_type": "ph",
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

Тело запроса:
```json
{
  "scenario": "optimize_ph",
  "duration_hours": 24,
  "parameters": {
    "target_ph": 6.5
  }
}
```

### 12.2. GET /api/simulations/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Получение результата симуляции.

---

## 13. WebSocket / Realtime

Для realtime-обновлений используется **Laravel Reverb** (встроенный WebSocket сервер).

**Подключение:**
- WebSocket endpoint: `ws://localhost:6001` (или `wss://` для HTTPS)
- Используется библиотека `laravel-echo` и `pusher-js` на клиенте
- Аутентификация через тот же токен, что и REST API

**Основные каналы:**

- `hydro.zones.{id}` — обновления по зоне (событие `ZoneUpdated`);
- `hydro.alerts` — новые алерты (событие `AlertCreated`);
- `nodes.{id}.status` — статусы узлов (событие `NodeStatusUpdated`).

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

## 14. Правила для ИИ-агентов

1. Все новые эндпоинты должны описываться здесь и в `REST_API_REFERENCE.md`.
2. Нельзя менять сигнатуру существующих эндпоинтов без явного указания версии (например, `/api/v2/`).
3. Все действия, влияющие на железо, должны проходить через Python-сервис (не ходить напрямую в MQTT из backend).
4. При добавлении нового эндпоинта обязательно указать требования аутентификации.
5. Публичные эндпоинты должны быть явно помечены как таковые.

Этот документ задаёт **единый контракт** между UI и backend и служит опорой для дальнейшего развития системы.
