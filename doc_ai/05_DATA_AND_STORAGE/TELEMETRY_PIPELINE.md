# TELEMETRY_PIPELINE.md
# Полная спецификация телеметрического конвейера (Pipeline)

Документ описывает путь телеметрии от узла ESP32 до UI/Android.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Цепочка телеметрии

```text
ESP32 → MQTT → Python Router → PostgreSQL → Laravel API/Inertia → Vue/Android → Пользователь
```

Узлы **никогда** не пишут напрямую в БД или Backend — только в MQTT.

---

## 2. Сообщения от узлов в MQTT

Формат топика: `hydro/{gh}/{zone}/{node}/{channel}/telemetry`.

Payload (пример):

```json
{
 "metric_type": "TEMPERATURE",
 "value": 23.4,
 "ts": 1737355600
}
```

**Обязательные поля:**
- `metric_type` (string, UPPERCASE) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LIGHT_INTENSITY`, `WATER_LEVEL`, `FLOW_RATE`, `PUMP_CURRENT` и т.д.
- `value` (float или int) — значение метрики
- `ts` (integer) — unix-время в секундах (не миллисекундах)

**Опциональные поля:**
- `unit` (string) — единица измерения
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг симулированного значения
- `stable` (boolean) — флаг стабильности значения

> **Важно:** Формат соответствует эталону node-sim. Поля `node_id` и `channel` не включаются в JSON, так как они уже есть в топике.

Частота публикаций настраивается (обычно 1–15 секунд).

---

## 3. MQTT Broker

- Используется единый брокер MQTT (Mosquitto/EMQX и т.п.).
- Python-сервис подписывается на `hydro/#` и обрабатывает сообщения.

---

## 4. Python Router → PostgreSQL

Python-сервис:

1. Принимает сообщение из MQTT.
2. Валидирует структуру JSON (формат, диапазоны).
3. Резолвит `sensor_id` через таблицу `sensors` (по `zone_id`, `node_id`, `metric_type`, `channel`, `scope`).
4. Преобразует во внутреннюю структуру (sensor_id, ts, value, quality, metadata, zone_id/cycle_id).
5. Записывает:

 - в таблицу `telemetry_samples` — полная история;
 - в таблицу `telemetry_last` — последнее значение по `sensor_id`.

Пример записи в `telemetry_samples` (логика, не SQL):

- `id`
- `sensor_id`
- `ts`
- `zone_id` (optional)
- `cycle_id` (optional)
- `value`
- `quality`
- `metadata`

---

## 5. Laravel → UI/Android

Backend предоставляет API:

- `/api/zones/{id}/telemetry/last` — последние значения;
- `/api/zones/{id}/telemetry/history` — историю по метрикам;
- `/api/nodes/{id}/telemetry/last` — последние значения по узлу.

Фронтенд и Android используют эти эндпоинты для графиков и карточек.

---

## 6. Retention и архивирование

Политика хранения задаётся в `DATA_RETENTION_POLICY.md` (отдельный документ).

В общем виде:

- последние N дней/месяцев — в основной БД;
- старые данные могут архивироваться/агрегироваться.

---

## 7. Правила для ИИ-агентов

1. Не расширять payload телеметрии произвольными полями без необходимости.
2. Любые изменения в структуре таблиц `telemetry_samples`/`telemetry_last`
 должны быть согласованы и задокументированы.
3. Нельзя писать в БД из ESP32 или фронтенда напрямую — только из Python-сервиса и Laravel.

Телеметрический pipeline — критический путь, и он должен оставаться простым и устойчивым.
