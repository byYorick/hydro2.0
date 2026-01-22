# EVENTS_AND_ALERTS_ENGINE.md
# Полная спецификация системы событий (Events) и тревог (Alerts)
# Инструкция для ИИ‑агентов, Python‑разработчиков и Laravel‑backend

Этот документ описывает, как работает система **событий (zone_events)** 
и **тревог (alerts)** в гидропонной системе 2.0.
Она отвечает за диагностику, автоматическое обнаружение проблем,
уведомления пользователя и взаимодействие контроллеров с UI.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общая концепция

### 1.1. Events (События)

**Событие** — это запись в журнале, фиксирующая важное изменение состояния системы или действия:

- действие контроллера (например, дозирование pH/EC, старт полива);
- изменение состояния устройства (онлайн/офлайн);
- изменение настроек пользователем;
- переход фазы рецепта.

События **не требуют обязательной реакции** и используются для:

- истории,
- аналитики,
- отладки.

Примеры типов событий (type):

- `PH_CORRECTED`
- `PH_TOO_HIGH_DETECTED`
- `PH_TOO_LOW_DETECTED`
- `EC_DOSING`
- `IRRIGATION_STARTED`
- `IRRIGATION_FINISHED`
- `CLIMATE_OVERHEAT`
- `CLIMATE_COOLING_ON`
- `CLIMATE_HEATING_ON`
- `LIGHT_ON`
- `LIGHT_OFF`
- `DEVICE_ONLINE`
- `DEVICE_OFFLINE`
- `RECIPE_PHASE_CHANGED`
- `ALERT_CREATED`
- `ALERT_RESOLVED`

---

### 1.2. Alerts (Алерты / тревоги)

**Алерт** — это состояние отклонения параметров от нормы, которое требует внимания.

Используются для:

- визуального предупреждения пользователя,
- возможной автоматической реакции (например, остановки полива),
- сигнализации о необходимости ручного вмешательства.

Примеры типов алертов:

- `PH_HIGH`
- `PH_LOW`
- `EC_LOW`
- `TEMP_HIGH`
- `TEMP_LOW`
- `HUMIDITY_HIGH`
- `HUMIDITY_LOW`
- `WATER_LEVEL_LOW`
- `NO_FLOW`
- `SENSOR_DISCONNECTED`
- `DEVICE_OFFLINE`
- `LIGHT_FAILURE`

Алерты имеют состояние:

- `ACTIVE` — тревога активна;
- `RESOLVED` — тревога закрыта (пользователем или автоматически).

---

## 2. Структура таблиц PostgreSQL

### 2.1. Таблица `zone_events`

```sql
CREATE TABLE zone_events (
 id BIGSERIAL PRIMARY KEY,
 zone_id BIGINT REFERENCES zones(id) ON DELETE CASCADE,
 type VARCHAR(64) NOT NULL,
 details JSONB,
 created_at TIMESTAMP(0) WITH TIME ZONE DEFAULT now()
);
```

**Назначение полей:**

- `zone_id` — зона, к которой относится событие;
- `type` — тип события (строка по справочнику);
- `details` — произвольные параметры (JSON), пример:
 ```json
 { "before": 6.3, "after": 5.9, "dose_ml": 0.5, "node_id": 12 }
 ```
- `created_at` — время регистрации события.

Рекомендуемые индексы:

```sql
CREATE INDEX zone_events_zone_id_created_at_idx
 ON zone_events(zone_id, created_at DESC);

CREATE INDEX zone_events_type_idx
 ON zone_events(type);
```

---

### 2.2. Таблица `alerts`

```sql
CREATE TABLE alerts (
 id BIGSERIAL PRIMARY KEY,
 zone_id BIGINT REFERENCES zones(id) ON DELETE CASCADE,
 type VARCHAR(64) NOT NULL,
 details JSONB,
 status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE / RESOLVED
 created_at TIMESTAMP(0) WITH TIME ZONE DEFAULT now(),
 resolved_at TIMESTAMP(0) WITH TIME ZONE
);
```

**Назначение полей:**

- `zone_id` — зона, в которой зафиксирована проблема;
- `type` — тип алерта (строка);
- `details` — JSON с параметрами (текущее значение, цель, node_id, и т.п.);
- `status` — `ACTIVE` или `RESOLVED`;
- `created_at` — время создания алерта;
- `resolved_at` — время закрытия алерта (если закрыт).

Рекомендуемые индексы:

```sql
CREATE INDEX alerts_zone_status_idx
 ON alerts(zone_id, status);

CREATE INDEX alerts_type_idx
 ON alerts(type);
```

---

## 3. Кто создаёт Events и Alerts

### 3.1. Python‑сервис

Создаёт:

- **Events**, связанные с автоматикой:
 - действия контроллеров (pH/EC/Climate/Irrigation/Light);
 - онлайн/офлайн статусы устройств (из MQTT status);
 - автопереходы фаз рецепта.
- **Alerts**, связанные с параметрами среды:
 - отклонения pH, EC, температуры, влажности;
 - авиарийные ситуации (нет потока, низкий уровень воды, не отвечает сенсор).

Python базируется на:

- `telemetry_last`,
- `zone_recipe_instances`,
- таблицах узлов/каналов.

### 3.2. Laravel‑backend

Создаёт:

- Events об активности пользователя:
 - ручной запуск полива;
 - ручное дозирование;
 - изменение рецепта/фазы;
 - ручное изменение настроек контроллеров.
- Обновляет Alerts:
 - изменяет статус на `RESOLVED`, когда пользователь вручную закрывает тревогу.

---

## 4. Примеры событий и алертов по контроллерам

### 4.1. pH Controller

**События:**

- `PH_CORRECTED`
 ```json
 {
 "before": 6.3,
 "after": 5.9,
 "dose_ml": 0.5,
 "direction": "acid",
 "node_id": 10
 }
 ```
- `PH_TOO_HIGH_DETECTED`
- `PH_TOO_LOW_DETECTED`

**Алерты:**

- `PH_HIGH`
 - создаётся, если `ph > target + 0.3` в течение N измерений;
- `PH_LOW`
 - создаётся, если `ph < target - 0.3`.

**Автоматическая логика (пример):**

```python
if ph > target + 0.3:
 ensure_alert(zone, "PH_HIGH", {"value": ph, "target": target})
elif ph < target - 0.3:
 ensure_alert(zone, "PH_LOW", {"value": ph, "target": target})
else:
 # опционально: можно авто‑закрывать, можно оставить пользователю
 pass
```

---

### 4.2. EC Controller

**События:**

- `EC_DOSING`
 ```json
 {
 "before": 1.2,
 "after": 1.4,
 "dose_ml": 3.0,
 "node_id": 11
 }
 ```

**Алерты:**

- `EC_LOW`
 - `ec < target - 0.15` в течение нескольких измерений.

---

### 4.3. Climate Controller

**События:**

- `CLIMATE_OVERHEAT`
- `CLIMATE_COOLING_ON`
- `CLIMATE_HEATING_ON`
- `FAN_ON`
- `FAN_OFF`

**Алерты:**

- `TEMP_HIGH` — `temp_air > target_temp + 2.0`
- `TEMP_LOW` — `temp_air < target_temp - 2.0`
- `HUMIDITY_HIGH` — `humidity > target_hum + 15`
- `HUMIDITY_LOW` — `humidity < target_hum - 15`

---

### 4.4. Irrigation Controller

**События:**

- `IRRIGATION_STARTED`
 ```json
 {
 "node_id": 15,
 "duration_sec": 10
 }
 ```
- `IRRIGATION_FINISHED`
 ```json
 {
 "node_id": 15,
 "actual_duration_sec": 9.8,
 "volume": 1.0
 }
 ```

**Алерты:**

- `WATER_LEVEL_LOW`
 - если показания level_sensor ниже порога;
- `NO_FLOW`
 - если насос включён > X сек, а датчик расхода показывает 0.

---

### 4.5. Lighting Controller

**События:**

- `LIGHT_ON`
- `LIGHT_OFF`
- `LIGHT_SCHEDULE_CHANGED`

**Алерты:**

- `LIGHT_FAILURE`
 - если свет должен быть включён (по расписанию), команда отправлена, 
 но показания light_sensor не отличаются от ночного уровня.

---

## 5. Логика жизненного цикла алертов

### 5.1. Создание алерта

Создаётся при выполнении условий:

1. Условие отклонения параметра от нормы выполняется;
2. Алёрт такого же `type` для зоны неактивен.

```python
def ensure_alert(zone, type, details):
 alert = find_active_alert(zone, type)
 if not alert:
 create_alert(zone, type, details)
 create_event(zone, "ALERT_CREATED", {"type": type, "details": details})
 else:
 update_alert_details(alert, details)
```

---

### 5.2. Обновление активного алерта

Если алерт уже активен, и параметр всё ещё вне нормы:

- не создаём новый алерт,
- обновляем поле `details` (например, более свежие значения),
- обновляем `updated_at`.

---

### 5.3. Закрытие алерта

**Варианты:**

1. **Ручное закрытие пользователем (рекомендуемый стандарт):**
 - в UI пользователь нажимает «Закрыть/Принять»;
 - Laravel выставляет:
 ```sql
 status = 'RESOLVED',
 resolved_at = now()
 ```
 - создаётся событие `ALERT_RESOLVED`.

2. **Автоматическое закрытие (опционально):**
 - при возврате параметра в безопасную зону,
 - Python‑сервис может автоматически изменить статус `RESOLVED`.

Рекомендуемый подход 2.0: 
**по умолчанию алерты закрывает пользователь** 
(для лучшей трассировки инцидентов).

---

## 6. Интеграция с Laravel и UI

### 6.1. Laravel backend

Контроллеры:

- `AlertController` (Web):
 - `index()` — список алертов;
 - `resolve()` — ручное закрытие алерта;
- `ZoneController@show()`:
 - отдаёт:
 - `zone`,
 - `alerts` (активные),
 - `events` (последние N).

### 6.2. Inertia / Vue

На странице зоны (`Zones/Show.vue`):

- Блок **Alerts**:
 - список активных алертов:
 - цветные бейджи по типу (critical/warning/info),
 - кнопка «Закрыть» (если политика разрешает).
- Блок **Events**:
 - таблица последних событий:
 - время,
 - тип,
 - краткое описание,
 - фильтры по типу и дате.

На странице Alerts (`Alerts/Index.vue`):

- фильтр по:
 - зоне,
 - типу,
 - статусу (ACTIVE/RESOLVED),
- возможность массового закрытия (опционально).

---

## 7. WebSockets и realtime‑уведомления

При использовании Laravel WebSockets / Echo:

- при создании алерта:
 - Laravel или Python инициируют событие `AlertCreated`;
- при обновлении или закрытии:
 - `AlertUpdated`, `AlertResolved`;
- Vue подписывается и обновляет список алертов в реальном времени.

ИИ‑агент может:

- предложить каналы и события вещания;
- реализовать подписку на стороне Vue.

---

## 8. Правила для ИИ‑агента

ИИ **может**:

- добавлять новые типы событий и алертов;
- расширять `details` дополнительными полями;
- улучшать условия срабатывания (например, по тренду, а не только по статике);
- добавлять новые UI‑представления событий/алертов;
- создавать агрегированные отчёты (по дням, зонам, типам).

ИИ **не может**:

- менять структуру таблиц `alerts` и `zone_events` с обратной несовместимостью;
- переименовывать существующие типы алертов/событий, нарушая историю;
- ломать логику соответствия типа и смысла (`PH_HIGH` всегда = повышенное pH);
- генерировать слишком частые события (спам в лог).

---

## 9. Чек‑лист перед изменением логики Events & Alerts

1. Новый тип события/алерта имеет уникальное и понятное имя? 
2. Условия его срабатывания чётко определены? 
3. Не дублирует ли он уже существующий тип? 
4. `details` содержит минимум:
 - текущее значение,
 - целевое значение (если применимо),
 - идентификатор узла/канала (если применимо)? 
5. Laravel и Vue смогут отобразить новый тип без падений? 
6. Создаётся ли событие `ALERT_CREATED` при создании алерта? 
7. Создаётся ли `ALERT_RESOLVED` при его закрытии? 
8. Нет ли риска бесконечного спама (множество событий/алертов за секунду)? 

---

# Конец файла EVENTS_AND_ALERTS_ENGINE.md
