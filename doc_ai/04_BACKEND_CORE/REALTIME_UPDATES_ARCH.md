# REALTIME_UPDATES_ARCH.md
# Архитектура реального времени для фронтенда и Android
# WebSocket / MQTT-bridge • Типы событий • Контракты

Документ дополняет:
- `../SYSTEM_ARCH_FULL.md`
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `API_SPEC_FRONTEND_BACKEND_FULL.md`
- `../12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md`

и описывает, как изменения состояния системы доставляются в UI
в **реальном или околореальном времени**.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Цели

1. Доставлять в UI (web + Android) актуальное состояние:
 - зон,
 - узлов,
 - алертов,
 - рецептов
 без постоянного опроса REST.
2. Поддерживать масштабирование по числу зон/узлов.
3. Оставаться совместимыми с существующей MQTT-инфраструктурой.

---

## 2. Общая схема

### 2.1. Backend — центральная точка истины

- Узлы публикуют телеметрию и статусы в MQTT (см. `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`).
- Backend:
 - подписывается на MQTT-топики,
 - агрегирует и нормализует данные,
 - хранит их в БД,
 - публикует «события для UI».

### 2.2. Канал к UI

Реализация через **Laravel Reverb** (встроенный WebSocket сервер):

- **WebSocket-соединение** от фронтенда/Android к backend:
 - endpoint: `ws://localhost:6001` (или `wss://` для HTTPS)
 - авторизация тем же токеном, что и REST API (Laravel Sanctum)
 - используется библиотека `laravel-echo` и `pusher-js` на клиенте

**Конфигурация:**
- Reverb автоматически запускается при старте Laravel контейнера
- Переменные окружения: `REVERB_APP_ID`, `REVERB_APP_KEY`, `REVERB_APP_SECRET`, `REVERB_PORT=6001`
- Подробнее см. `FULL_STACK_DEPLOY_DOCKER.md`, раздел 13

**Альтернативы (не используются в текущей версии):**
- MQTT-bridge для фронта (если будет использоваться MQTT-клиент в UI)
- Внешний WS-gateway

---

## 3. Модель событий

### 3.1. Общее сообщение

Каждое событие, летящее в UI, имеет схему:

```json
{
 "event_type": "string",
 "event_id": "uuid",
 "occurred_at": "ISO8601 timestamp",
 "payload": { }
}
```

- `event_type` — тип события (см. ниже).
- `event_id` — уникальный ID для идемпотентности.
- `occurred_at` — время возникновения в системе.
- `payload` — структура зависит от `event_type`.

### 3.2. Базовые типы событий

1. `zone_state_updated`
 - обновление агрегированного состояния зоны.

2. `node_status_updated`
 - изменение статуса узла (online/offline/degraded/maintenance).

3. `telemetry_batch_updated`
 - пакетное обновление телеметрии по зоне (batched realtime).

4. `alert_created`
 - новый алерт.

5. `alert_updated`
 - изменение статуса алерта (подтверждён, закрыт и т.п.).

6. `recipe_assigned_to_zone`
 - назначен новый рецепт зоне.

7. `recipe_stage_changed`
 - переход стадии рецепта.

При необходимости добавляются новые типы, но без ломки старых.

---

## 4. Примеры payload’ов

### 4.1. zone_state_updated

```json
{
 "event_type": "zone_state_updated",
 "event_id": "uuid-123",
 "occurred_at": "2025-01-01T12:00:00Z",
 "payload": {
 "zone_id": "zone-1",
 "greenhouse_id": "gh-1",
 "metrics": {
 "ph": 6.2,
 "ec": 1.8,
 "solution_temp": 20.5,
 "air_temp": 24.0,
 "air_humidity": 55.0,
 "co2": 650
 },
 "status": "ok", 
 "active_recipe_id": "recipe-123",
 "active_recipe_stage": "vegetative"
 }
}
```

### 4.2. node_status_updated

```json
{
 "event_type": "node_status_updated",
 "event_id": "uuid-456",
 "occurred_at": "2025-01-01T12:00:05Z",
 "payload": {
 "node_id": "node-1234",
 "zone_id": "zone-1",
 "greenhouse_id": "gh-1",
 "status": "online",
 "rssi": -65,
 "fw_version": "2.0.1"
 }
}
```

### 4.3. telemetry_batch_updated

```json
{
 "event_type": "telemetry_batch_updated",
 "event_id": "uuid-777",
 "occurred_at": "2025-01-01T12:00:10Z",
 "payload": {
 "zone_id": "zone-1",
 "updates": [
   {
     "node_id": "node-1234",
     "metric_type": "PH",
     "channel": "ph_sensor",
     "value": 6.2,
     "ts": 1735732810000
   }
 ]
 }
}
```

### 4.4. alert_created

```json
{
 "event_type": "alert_created",
 "event_id": "uuid-789",
 "occurred_at": "2025-01-01T12:01:00Z",
 "payload": {
 "alert_id": "alert-1",
 "severity": "critical",
 "alert_type": "ph_out_of_range",
 "zone_id": "zone-1",
 "greenhouse_id": "gh-1",
 "related_node_ids": ["node-1234"],
 "message": "pH 5.0 below target 6.0–6.5",
 "suggested_actions": [
 "check acid/base dosing pumps",
 "inspect pH sensor"
 ]
 }
}
```

---

## 5. Подписка/фильтрация на стороне UI

Клиент после установления WebSocket-сессии отправляет команду подписки:

```json
{
 "action": "subscribe",
 "channels": [
 {
 "type": "greenhouse",
 "id": "gh-1"
 }
 ],
 "event_types": [
 "zone_state_updated",
 "telemetry_batch_updated",
 "node_status_updated",
 "alert_created",
 "alert_updated"
 ]
}
```

Правила:

- по умолчанию подписка ограничена теми объектами,
 к которым у пользователя есть доступ;
- backend может реализовать предустановленные «пакеты» подписок:
 - `dashboard_basic` — минимально необходимые события для дашборда;
 - `zone_details(zone_id)` — расширенный набор.

---

## 6. Обработка на backend

Backend-реализация (на уровне принципов):

1. Слушает MQTT-топики от узлов.
2. На каждое значимое изменение:
 - обновляет состояние БД,
 - формирует одно или несколько событий UI (описанных выше).
3. В «реалтайм-слое»:
 - мапит события на подключённых WebSocket-клиентов
 по greenhouse/zone/role.

Важно:

- для производительности использовать очередь/стрим (например, Redis Streams, Kafka, internal queue)
 между обработкой MQTT и WebSocket-пушами, если нагрузка высокая.

---

## 7. Связь с push-уведомлениями

- События `alert_created` и `alert_updated` также используются
 слоем уведомлений (см. `../06_DOMAIN_ZONES_RECIPES/ALERTS_AND_NOTIFICATIONS_CHANNELS.md`).
- Push-уведомления выбирают подмножество этих событий
 по правилам пользователя (критичность, зоны).

---

## 8. Требования к ИИ-агенту

1. Нельзя придумывать новые «магические» типы событий,
 не описав их здесь и в связанных спеках.
2. Любые изменения в структуре payload должны быть:
 - отражены в этом документе,
 - синхронизированы с фронтендом и Android (`../12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md`).
3. При добавлении нового event_type:
 - описать, при каких условиях backend его генерирует,
 - описать ожидаемую реакцию UI (обновление дашборда, список алертов и т.п.).
