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

### 2.1. POST /api/auth/login

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

- Выход: `{"status": "ok"}`

### 2.3. GET /api/auth/me

- Возвращает текущего пользователя и его права.

---

## 3. Greenhouses / Zones / Nodes

### 3.1. GET /api/greenhouses

- Список теплиц с краткой информацией.

### 3.2. POST /api/greenhouses

- Создание теплицы.

### 3.3. GET /api/greenhouses/{id}

- Детальная информация + связанные зоны.

### 3.4. GET /api/zones

- Список зон (с фильтрами по теплице, статусу и т.п.).

### 3.5. GET /api/zones/{id}

MVP-реализация (для Inertia props страниц):

- `GET /api/zones` — плоский список зон `{id,name,status,crop,phase}`.

- Полная карточка зоны:
 - конфигурация;
 - активный рецепт и фаза;
 - привязанные узлы и каналы;
 - последние значения ключевых метрик.

### 3.6. POST /api/zones

- Создание зоны.

### 3.7. PATCH /api/zones/{id}

- Обновление параметров зоны (название, тип, лимиты и т.п.).

### 3.8. GET /api/nodes

- Список узлов ESP32, их статус (online/offline), привязка к зонам.

### 3.9. GET /api/nodes/{id}

- Детальная информация об узле:
 - NodeConfig;
 - список каналов;
 - последняя телеметрия.

---

## 4. Recipes API

### 4.1. GET /api/recipes

- Список рецептов (фильтры по типу культур, активности).

### 4.2. POST /api/recipes

- Создание рецепта и базового набора фаз.

### 4.3. GET /api/recipes/{id}

- Детальное описание рецепта + фазы.

### 4.4. PATCH /api/recipes/{id}

- Обновление рецепта (описание, культура и т.п.).

### 4.5. POST /api/recipes/{id}/phases

- Добавление фазы к рецепту.

### 4.6. PATCH /api/recipe-phases/{id}

- Обновление параметров фазы (цели pH, EC, продолжительность и т.п.).

### 4.7. POST /api/zones/{id}/attach-recipe

- Назначение рецепта на зону.
- Тело:

```json
{
 "recipe_id": 1,
 "start_at": "2025-11-15T10:00:00Z"
}
```

### 4.8. POST /api/zones/{id}/change-phase

- Ручной переход зоны на другую фазу.

---

## 5. Telemetry & History API

### 5.1. GET /api/zones/{id}/telemetry/last

- Последние значения ключевых метрик по зоне.

### 5.2. GET /api/zones/{id}/telemetry/history

Параметры:

- `metric` — например, `PH`, `EC`, `TEMP_AIR`;
- `from`, `to` — временной диапазон.

Ответ — массив точек для графика.

### 5.3. GET /api/nodes/{id}/telemetry/last

- Последняя телеметрия по канальным метрикам узла.

---

## 6. Commands API

### 6.1. POST /api/zones/{id}/commands

- Отправка команд на зону (через Python-сервис).
- Примеры команд:
 - `FORCE_IRRIGATION`;
 - `FORCE_DRAIN`;
 - `FORCE_LIGHT_ON/OFF`;
 - `ZONE_PAUSE/RESUME`.

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

- Низкоуровневые команды для конкретного узла (диагностика, калибровка).

---

## 7. Alerts & Events API

### 7.1. GET /api/alerts

- Список активных/исторических алертов.

### 7.2. PATCH /api/auth/alerts/{id}/ack
- Требует роль `operator` или `admin`.

### 7.3. GET /api/auth/alerts

- Возвращает список алертов для UI (аутентифицированный доступ).


- Подтверждение алерта оператором.

---

## 8. System & AI API (примерный контракт)

### 8.1. GET /api/system/config/full

- Полная конфигурация теплиц/зон/узлов/каналов для Python/AI.

### 8.2. POST /api/ai/recipe/suggest

- Запрос от AI-сервиса на предложение рецепта для заданной культуры/условий.

### 8.3. POST /api/ai/diagnostics/run

- Запуск диагностики системы (анализ телеметрии, событий).

---

## 9. WebSocket / Realtime

Для realtime-обновлений могут использоваться:

- Laravel WebSockets;
- или внешний WS-gateway.

Основные каналы (MVP):

- `hydro.zones.{id}` — обновления по зоне (событие ZoneUpdated);
- `hydro.alerts` — новые алерты (событие AlertCreated);
- `nodes.{id}.status` — статусы узлов (резерв).

---

## 10. Правила для ИИ-агентов

1. Все новые эндпоинты должны описываться здесь и в `REST_API_REFERENCE.md`.
2. Нельзя менять сигнатуру существующих эндпоинтов без явного указания версии (например, `/api/v2/ `).
3. Все действия, влияющие на железо, должны проходить через Python-сервис (не ходить напрямую в MQTT из backend).

Этот документ задаёт **единый контракт** между UI и backend и служит опорой для дальнейшего развития системы.
