# План доработок backend-системы hydro2.0

Документ фиксирует план доработок backend-а, сервисов и БД с учётом:

- перехода на монолитный Laravel как **api-gateway + device-registry**;
- единой точки записи телеметрии и команд через **history-logger**;
- полной интеграции **Digital Twin**;
- безопасного управления насосами (no_flow / overcurrent / dry_run / pump_stuck_on);
- учёта того, что **главный насос циркуляции включён через нормально-замкнутое реле (NC)** и при падении электроники работает непрерывно;
- замкнутой гидропонной системы с **циркуляцией** и **плановой сменой воды по расписанию**;
- стандартизации alerts, metric_type и работы с `telemetry_last`.

---

## 1. Архитектура и ответственность слоёв

### 1.1. Laravel

Laravel выполняет роли:

- **API Gateway** для web/mobile:
  - Auth (Sanctum).
  - CRUD: пользователи, теплицы, зоны, ноды, пресеты, рецепты, урожай, отчёты.
  - REST API для симуляций (Digital Twin).
- **Device Registry**:
  - регистрация нод,
  - привязка к зонам,
  - хранение firmware/hardware информации.
- **Только читает**:
  - телеметрию (`telemetry_*`),
  - команды (`commands`),
  - алерты (`alerts`),
  - события (`zone_events`),
  - логи ИИ/планировщика.

Laravel **НЕ пишет**:

- сырую телеметрию,
- `telemetry_last`,
- статусы команд,
- агрегированные телеметрии.

### 1.2. Python-сервисы

- `history-logger` — **единственный вход** телеметрии и ответов на команды:
  - пишет `telemetry_samples`, `telemetry_last`, `alerts` (частично), `zone_events`;
  - обновляет статусы в `commands`.
- `mqtt-bridge` — HTTP→MQTT мост:
  - принимает запрос от Laravel/automation,
  - создаёт запись команды (через общий код),
  - публикует команду в MQTT.
- `automation-engine`:
  - читает `telemetry_last` / `zones` / `recipes`,
  - решает, когда включать циркуляцию, смену воды, дозаторы, климат,
  - генерирует команды (через `mqtt-bridge`/MQTT),
  - пишет `alerts`, `zone_events`, `ai_logs`.
- `scheduler`:
  - расписания (время смены воды, ночные/дневные режимы),
  - периодические задачи по зонам и насосам.
- `digital-twin`:
  - HTTP API для симуляции рецептов/зон.
- `telemetry-aggregator` (новый):
  - агрегирует `telemetry_samples` в `telemetry_agg_1m/1h/daily`.

---

## 2. REST-ингест телеметрии через history-logger

### 2.1. Общий обработчик телеметрии

Создать модуль `backend/services/common/telemetry.py`:

- Модель входных данных:

```python
class TelemetrySampleModel(BaseModel):
    node_uid: str
    zone_uid: str | None = None
    metric_type: str
    value: float
    ts: datetime
    raw: dict | None = None
```

- Общая функция:

```python
async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
    """
    1. По node_uid/zone_uid находим node_id, zone_id.
    2. Проверяем, что нода зарегистрирована и validated.
    3. Нормализуем metric_type (см. §7).
    4. Пишем в telemetry_samples.
    5. Обновляем telemetry_last (zone_id, node_id, metric_type).
    """
```

Эту функцию используют:

- MQTT-подписчик в history-logger,
- HTTP-ингест-эндпоинт.

### 2.2. HTTP API в history-logger

В `backend/services/history-logger/main.py`:

```python
@app.post("/ingest/telemetry")
async def ingest_telemetry(req: IngestRequest):
    await process_telemetry_batch(req.samples)
    return {"status": "ok", "count": len(req.samples)}
```

`IngestRequest` содержит массив `TelemetrySampleModel`.

### 2.3. Laravel-ингест = тонкая прокладка

В Laravel:

`PythonIngestController@telemetry`:

- валидирует JSON,
- проксирует payload в history-logger (`/ingest/telemetry`) через `Http::post()`,
- сам не пишет в БД.

Laravel перестаёт записывать телеметрию напрямую.

---

## 3. Monolith: api-gateway и device-registry в Laravel

### 3.1. Деактивация лишних сервисов

В `backend/docker-compose.dev.yml`:

- удалить/закомментировать сервисы `api-gateway`, `device-registry`.

В `backend/services/api-gateway` и `backend/services/device-registry`:

- добавить README с пометкой `LEGACY / NOT USED`.

### 3.2. Обновление документации

В `doc_ai` и архитектурных схемах:

- явно указать:
  - "API Gateway реализован в Laravel";
  - "Device registry реализован в Laravel (NodeRegistryService)".
- Обновить схемы, убрав устаревшие микросервисы.

---

## 4. Полная интеграция Digital Twin

### 4.1. docker-compose

Добавить сервис `digital-twin` в `backend/docker-compose.dev.yml`:

```yaml
digital-twin:
  build:
    context: ./services/digital-twin
  environment:
    - PG_HOST=db
    - PG_USER=...
    - PG_PASSWORD=...
    - PG_DATABASE=...
  depends_on:
    - db
```

### 4.2. Клиент в Laravel

Создать `DigitalTwinClient`:

- читает `DIGITAL_TWIN_URL` из `.env` / `config/services.php`,
- метод:

```php
public function simulateZone(int $zoneId, array $params): array;
```

### 4.3. API для фронта/мобилки

Добавить `SimulationController`:

- `POST /api/zones/{zone}/simulate`:
  - валидирует входной сценарий (duration_days, initial_state, др.),
  - вызывает `DigitalTwinClient`,
  - отдаёт ответ.

---

## 5. Python = единственный писатель телеметрии и команд

### 5.1. Запрет записи телеметрии в Laravel

Нужно найти и убрать/задепрекейтить любые записи в:

- `telemetry_samples`,
- `telemetry_agg_*`,
- `telemetry_last`

из Laravel: модели, репозитории, контроллеры.

Laravel только читает эти таблицы.

### 5.2. Запрет прямого изменения статусов команд в Laravel

Статусы `commands.status` меняет только Python:

- через history-logger / общий модуль `common.commands`:
  - `mark_command_sent`,
  - `mark_command_ack`,
  - `mark_command_failed`,
  - `mark_timeouts`.

Laravel может:

- создавать логические "заказы" команд (отдельная сущность/таблица),
- инициировать команды через HTTP в `mqtt-bridge`,
- отображать статусы, но не править их.

---

## 6. Регистрация и валидация нод (device-registry в Laravel)

### 6.1. Расширение таблицы nodes

Добавить поля:

- `validated` (bool, default false),
- `first_seen_at` (timestamp, nullable),
- `firmware_version` (string, nullable),
- `hardware_revision` (string, nullable).

### 6.2. NodeRegistryService

Создать `NodeRegistryService` в Laravel:

```php
public function registerNode(string $nodeUid, ?string $zoneUid, array $attributes = []): Node
```

Логика:

- По `nodeUid` ищем/создаём `Node`.
- Если `zoneUid` задан:
  - находим `Zone` по uid,
  - назначаем `zone_id`.
- Обновляем:
  - `first_seen_at` (если не было),
  - `firmware_version`,
  - `hardware_revision`.
- Ставим `validated = true`.
- Сохраняем и возвращаем `Node`.

### 6.3. API регистрации ноды

`POST /api/nodes/register`:

- тело: `node_uid`, `zone_uid` (опц.), `firmware_version`, `hardware_revision`,
- вызывает `NodeRegistryService::registerNode`,
- возвращает `NodeResource`.

### 6.4. Связь с history-logger

В history-logger (в `process_telemetry_batch`):

- по `node_uid` читаем `nodes`:
  - если записи нет → логируем `unknown node` и игнорируем телеметрию;
  - если `validated = false` → логируем и игнорируем телеметрию.

Телеметрия учитывается только от зарегистрированных и валидированных нод.

---

## 7. Единый словарь metric_type

### 7.1. Python: common/metrics.py

Создать Enum:

```python
class Metric(str, Enum):
    PH = "ph"
    EC = "ec"
    TEMP_AIR = "temp_air"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LUX = "lux"
    WATER_LEVEL = "water_level"
    FLOW_RATE = "flow_rate"
    PUMP_CURRENT = "pump_current"
    # при необходимости другие
```

Словарь и ошибка:

```python
CANONICAL_METRICS = {m.value: m for m in Metric}

class UnknownMetricError(Exception):
    ...
```

Функция нормализации:

```python
def normalize_metric_type(raw: str) -> str:
    key = raw.strip().lower()
    if key in CANONICAL_METRICS:
        return CANONICAL_METRICS[key].value
    raise UnknownMetricError(raw)
```

Все Python-сервисы используют только значения из этого Enum.

### 7.2. Laravel: enum MetricType

Создать `app/Enums/MetricType.php`:

```php
enum MetricType: string
{
    case PH = 'ph';
    case EC = 'ec';
    case TEMP_AIR = 'temp_air';
    case HUMIDITY = 'humidity';
    case CO2 = 'co2';
    case LUX = 'lux';
    case WATER_LEVEL = 'water_level';
    case FLOW_RATE = 'flow_rate';
    case PUMP_CURRENT = 'pump_current';
}
```

Модели/репозитории должны использовать `MetricType` вместо "магических" строк.

### 7.3. Применение в history-logger и REST-ингесте

Перед записью в БД:

- `metric_type = normalize_metric_type(sample.metric_type)`,
- при `UnknownMetricError`:
  - логируем событие,
  - не пишем телеметрию,
  - опционально создаём alert (`unknown_metric`).

---

## 8. telemetry_last с node_id

### 8.1. DB-изменения

Добавить поле `node_id` в `telemetry_last`.

Заменить constraint на:

```sql
UNIQUE (zone_id, node_id, metric_type)
```

### 8.2. Обновление логики

В общем коде (например, `common/db.py`):

```python
async def upsert_telemetry_last(zone_id, node_id, metric_type, value, raw, ts):
    await conn.execute(
        """
        INSERT INTO telemetry_last (zone_id, node_id, metric_type, value, raw, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (zone_id, node_id, metric_type)
        DO UPDATE SET value = EXCLUDED.value,
                      raw = EXCLUDED.raw,
                      updated_at = EXCLUDED.updated_at
        """,
        zone_id, node_id, metric_type, value, json.dumps(raw), ts,
    )
```

Automation-engine и Laravel могут:

- агрегировать по зоне (игнорируя `node_id`),
- проводить диагностику по нодам.

---

## 9. Alerts: source + code, бизнес vs инфраструктура

### 9.1. Структурный признак source

В таблицу `alerts` добавить поле `source`:

- `'biz'` — бизнес-алерты (pH, EC, no_flow, overcurrent, dry_run, pump_stuck_on),
- `'infra'` — инфраструктурные (MQTT down, DB unreachable, service down).

### 9.2. code vs type

- `code` — машинный код (`biz_no_flow`, `biz_overcurrent`, `infra_mqtt_down`, и т.д.),
- `type` — человекочитаемый текст для UI.

### 9.3. Стандартизированные коды

**Бизнес:**

- `biz_no_flow` — нет потока воды при работе насоса.
- `biz_overcurrent` — превышение тока по INA209.
- `biz_dry_run` — попытка работы насоса при слишком низком уровне воды.
- `biz_pump_stuck_on` — насос должен быть OFF, но ток/поток есть (залипшее NC-реле).
- `biz_high_ph`, `biz_low_ph`.
- `biz_high_ec`, `biz_low_ec`.

**Инфраструктура:**

- `infra_mqtt_down`,
- `infra_db_unreachable`,
- `infra_service_down_<name>`.

---

## 10. Модель воды: замкнутый контур и смена воды

### 10.1. Общая идея

Для каждой зоны/резервуара:

- вода находится в замкнутом контуре (резервуар → стеллажи → обратно),
- есть два режима:
  - **Циркуляция (recirculation)** — главный насос гоняет раствор по кругу.
  - **Смена раствора (water_change)** — по расписанию/по условиям:
    - слив (drain),
    - заполнение (fill),
    - стабилизация (stabilize).

### 10.2. Настройки зоны (water_cycle)

В `zones.settings` (или отдельной таблице) описать:

```json
"water_cycle": {
  "mode": "RECIRCULATING",
  "recirc": {
    "enabled": true,
    "schedule": [
      { "from": "00:00", "to": "23:59", "duty_cycle": 0.5 }
    ],
    "max_recirc_off_minutes": 10
  },
  "water_change": {
    "enabled": true,
    "interval_days": 7,
    "time_of_day": "09:00",
    "max_solution_age_days": 10,
    "trigger_by_ec_drift": true,
    "ec_drift_threshold": 30
  }
}
```

Также можно добавить цели по смене раствора в `recipes/recipe_phases` (например, `ideal_change_interval_days`).

### 10.3. Состояния water state machine

Для зоны:

- `NORMAL_RECIRC`
- `WATER_CHANGE_DRAIN`
- `WATER_CHANGE_FILL`
- `WATER_CHANGE_STABILIZE`

Переходы:

```
NORMAL_RECIRC
   | (по расписанию / возрасту раствора / EC-дрифту)
   v
WATER_CHANGE_DRAIN -> WATER_CHANGE_FILL -> WATER_CHANGE_STABILIZE
   ^                                              |
   |----------------------------------------------+
```

---

## 11. Главный насос: нормально-замкнутое реле (NC)

### 11.1. Конфиг каналов

В описании каналов ноды насоса:

```json
{
  "id": "pump_recirc",
  "type": "pump",
  "fail_safe_mode": "NC",
  "controlled_by": "relay",
  "relay_logic": "active_open"
}
```

Для других насосов:

```json
{
  "id": "pump_drain",
  "type": "pump",
  "fail_safe_mode": "NO",
  "controlled_by": "relay",
  "relay_logic": "active_close"
}
```

### 11.2. Поведение при падении электроники

При полной потере управления (контроллер умер, выходы не управляют реле):

- NC-реле `pump_recirc` отпускает,
- контакты замыкаются,
- насос циркуляции работает непрерывно,
- растения не остаются без движения воды.

---

## 12. Логика циркуляции (recirculation) с учётом NC-насоса

### 12.1. Принцип

Для обычного насоса автоматика реализует duty как чередование включения/выключения.

Для NC насоса "по умолчанию ON", автоматике нужно:

- в норме оставлять насос включённым;
- реализовывать duty как вставку периодов OFF (размыкание реле);
- иметь ограничение `max_recirc_off_minutes` — сколько максимум можно подряд держать OFF.

### 12.2. Псевдокод управления recirc

```python
async def tick_recirculation(zone):
    cfg = zone.settings["water_cycle"]["recirc"]
    if not cfg["enabled"]:
        # хотим behavior по умолчанию: насос ON (NC), не трогаем реле
        return

    if not in_schedule_window(now, cfg["schedule"]):
        desired_state = "OFF"
    else:
        desired_state = decide_recirc_state_by_duty(cfg, now)  # с учётом duty_cycle

    # ограничиваем длительность OFF
    if desired_state == "OFF" and off_duration(zone, "pump_recirc") > cfg["max_recirc_off_minutes"]:
        desired_state = "ON"

    if desired_state == "OFF":
        await set_relay_state("pump_recirc", "OPEN")   # отключаем насос
    else:
        await set_relay_state("pump_recirc", "CLOSED") # включаем насос
```

При падении контроллера:

- реле возвращается в "неуправляемое" состояние,
- насос работает постоянно (fail-safe).

---

## 13. Плановая смена раствора (water_change)

### 13.1. Условия запуска

В scheduler для каждой зоны:

- если `water_cycle.water_change.enabled == true`, и:
  - прошло `interval_days` с `solution_started_at`, или
  - `solution_age > max_solution_age_days`, или
  - EC-дрифт превысил `ec_drift_threshold` несмотря на корректировки,
- переводим зону в `WATER_CHANGE_DRAIN`.

### 13.2. Алгоритм смены

**WATER_CHANGE_DRAIN:**

- автоматика осознанно выключает recirc-насос:
  - `set_relay_state("pump_recirc", "OPEN")`,
- запускает `pump_drain`/дренаж:
  - следит за `water_level`, пока не достигнут порог "пусто",
  - следит за `no_flow`/`overcurrent`,
  - при успехе → `WATER_CHANGE_FILL`, при ошибке → `FAILED`.

**WATER_CHANGE_FILL:**

- включает `pump_fill`/клапан,
- контролирует `water_level` до `target_level`,
- может частично корректировать EC/pH (через дозаторы),
- при успехе → `WATER_CHANGE_STABILIZE`.

**WATER_CHANGE_STABILIZE:**

- ждёт X минут, пока параметры устаканятся,
- фиксирует pH/EC/temperature,
- ставит `solution_started_at = now`,
- пишет `zone_event` типа `WATER_CHANGE_COMPLETED`,
- возвращает зону в `NORMAL_RECIRC`.

При полном падении электроники:

- fail-safe: recirc-насос включается постоянно;
- смена воды считается незавершённой, требует ручного вмешательства после восстановления.

---

## 14. Безопасность насосов: no_flow / overcurrent / dry_run / pump_stuck_on

### 14.1. Overcurrent

**Источник данных:**

- прошивка `pump_node` с INA209:
  - при `run_pump` меряет ток,
  - если ток > порога:
    - останавливает насос,
    - отправляет `command_response`:

```json
{
  "cmd": "run_pump",
  "cmd_id": "...",
  "status": "ERROR",
  "error_code": "overcurrent",
  "details": {
    "channel": "pump_recirc",
    "current_ma": 2300,
    "threshold_ma": 1500
  }
}
```

**history-logger:**

- ставит `commands.status = 'failed'`,
- создаёт alert:

```python
create_alert(
    zone_id=zone_id,
    source='biz',
    code='biz_overcurrent',
    type='Overcurrent on pump channel',
    details=details,
)
```

### 14.2. no_flow

В модуле `common/water_flow.py`:

- по телеметрии `flow_rate` и/или `water_level`:

```python
async def check_no_flow(zone_id, pump_channel, cmd_id, telemetry_window):
    # Вариант A: есть flow-сенсор
    # Вариант B: по delta water_level до/после полива/циркуляции
```

- при отсутствии потока при включённом насосе создаём:

```python
create_alert(
    zone_id=zone_id,
    source='biz',
    code='biz_no_flow',
    type='No water flow detected',
    details=...
)
```

### 14.3. dry_run

Перед попыткой включить насос:

- проверяем `water_level`:

```python
water_level = await get_latest_metric(zone_id, "water_level")
if water_level is not None and water_level < MIN_WATER_LEVEL:
    create_alert(
        zone_id=zone_id,
        source='biz',
        code='biz_dry_run',
        type='Dry run protection activated',
        details={"water_level": water_level, "min_level": MIN_WATER_LEVEL},
    )
    # насос не запускаем
    return False
```

### 14.4. pump_stuck_on с учётом NC-реле

**Сценарий:**

- автоматика думает, что насос OFF (relay OPEN),
- а по телеметрии ток/flow > порога → реле залипло или есть обход.

В `history-logger/water_flow`:

```python
if desired_state == "OFF" and current_ma > CURRENT_IDLE_THRESHOLD:
    create_alert(
        zone_id=zone_id,
        source='biz',
        code='biz_pump_stuck_on',
        type='Recirculation pump stuck ON',
        details={...},
    )
```

Это критический alert, требующий ручного осмотра железа.

---

## 15. Статистика по расходу воды

### 15.1. Таблицы

**water_usage_logs:**

- `zone_id`, `node_id`, `pump_channel`,
- `cmd_id`,
- `volume_l` (рассчитанный объём),
- `duration_ms`,
- `avg_flow_l_min`,
- `details` (json),
- `started_at`, `finished_at`.

**water_usage_daily:**

- `date`, `zone_id`,
- `total_volume_l`,
- `irrigation_count`.

### 15.2. Кто пишет

**water_flow / scheduler:**

- после каждого цикла полива/циркуляции, где можно оценить объём:

```python
volume_l = calculate_volume(flow_data, duration_s)
insert_water_usage_log(...)
```

**Агрегация:**

- либо через `telemetry-aggregator`,
- либо отдельной задачей в `scheduler`.

---

## 16. Safe automation (безопасное автоуправление)

### 16.1. Общая функция

Перед любой командой `run_pump` (recirc, drain, fill):

```python
async def can_run_pump(zone_id, pump_channel):
    alerts = await get_active_alerts(zone_id)
    critical_codes = {"biz_overcurrent", "biz_no_flow", "biz_dry_run"}

    if any(a.code in critical_codes for a in alerts):
        return False

    water_level = await get_latest_metric(zone_id, "water_level")
    if water_level is not None and water_level < MIN_WATER_LEVEL:
        create_alert(... biz_dry_run ...)
        return False

    if too_many_recent_failures(zone_id, pump_channel):
        return False

    return True
```

`scheduler` и `automation-engine` обязаны вызывать `can_run_pump` перед запуском насосов.

### 16.2. Сброс блокировки

**Оператор в UI:**

- видит активные alerts (`biz_overcurrent`, `biz_no_flow`, `biz_dry_run`, `biz_pump_stuck_on`),
- устраняет проблему,
- нажимает "Reset safety lock".

**Backend:**

- резолвит соответствующие alerts (`status = RESOLVED`),
- автоматика снова может запускать насосы.

---

## 17. Новый сервис telemetry-aggregator

### 17.1. Роль

Периодически агрегирует `telemetry_samples` в:

- `telemetry_agg_1m`,
- `telemetry_agg_1h`,
- `telemetry_daily`.

### 17.2. Логика

Ввести таблицу `aggregator_state`:

- хранит `last_ts_1m`, `last_ts_1h`, `last_ts_daily`.

**Сервис telemetry-aggregator:**

- раз в N секунд/минут:
  - читает `last_ts_*`,
  - выполняет `INSERT ... SELECT` с `time_bucket('1 minute', ts)` / `1 hour` / `1 day`,
  - обновляет `aggregator_state`.

---

---

## Статус выполнения (обновлено: 2025-01-27)

### ✅ Выполнено

1. **NodeConfig с gh_uid и zone_uid (версия 3)**
   - Обновлена спецификация `NODE_CONFIG_SPEC.md`
   - Реализовано в `config_storage` компоненте
   - Интегрировано во все типы нод (ph_node, ec_node, climate_node, pump_node)
   - Обновлён генератор конфигураций в Laravel (`NodeConfigService`)

2. **Relay Driver и Pump Driver**
   - Создан компонент `relay_driver` для управления реле (NC/NO)
   - Создан компонент `pump_driver` с интеграцией INA209
   - Интегрировано в `climate_node` (relay_driver)
   - Интегрировано в `ec_node` и `pump_node` (pump_driver)

3. **INA209 интеграция в pump_node**
   - Проверка тока при запуске насоса (overcurrent, no-flow)
   - Периодический опрос тока и публикация телеметрии `pump_bus_current`
   - Пороги из NodeConfig (`limits.currentMin`, `limits.currentMax`)

4. **Setup Portal (Provisioning)**
   - Реализовано для всех типов нод
   - AP режим с веб-интерфейсом
   - Автоматическая генерация PIN из MAC-адреса

5. **Graceful переподключение Wi-Fi/MQTT**
   - Реализовано во всех типах нод (`ph_node`, `ec_node`, `climate_node`, `pump_node`) при изменении NodeConfig
   - Graceful остановка и переподключение с новыми параметрами
   - Проверка изменений Wi-Fi и MQTT параметров перед сохранением конфига

6. **Water Cycle Engine**
   - Реализована проверка EC drift (сравнение начального и текущего значения)
   - Улучшена логика duty_cycle (циклы по 10 минут)
   - Фиксация параметров после стабилизации при смене воды
   - Интеграция с pump_safety

7. **Pump Safety Engine**
   - Проверка MCU offline (статус узла и последняя телеметрия)
   - Получение порогов из конфигурации узла (`get_pump_thresholds`)
   - Улучшенная проверка pump_stuck_on с учётом типов насосов

### 🔄 В процессе / Планируется

- Базовая калибровка Digital Twin по историческим данным (опционально для MVP)
- E2E тестирование полной цепочки
- Дополнение unit-тестов

---

Этот файл должен храниться в репозитории (например, `backend/BACKEND_REFACTOR_PLAN.md`) и служить единым источником правды по доработкам backend'а и логики воды.
