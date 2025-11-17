# План рефакторинга backend-системы hydro2.0

**Дата создания:** 2025-01-27  
**Основа:** `BACKEND_REFACTOR_PLAN.md` + аудит текущего состояния

---

## Резюме текущего состояния

### Что уже работает

1. **Laravel как API Gateway** ✅
   - REST API реализован
   - Авторизация через Sanctum
   - CRUD для всех сущностей

2. **Python-сервисы** ✅
   - `history-logger` — получает телеметрию из MQTT, пишет в БД
   - `automation-engine` — управление зонами
   - `scheduler` — расписания
   - `mqtt-bridge` — HTTP→MQTT мост

3. **База данных** ✅
   - PostgreSQL + TimescaleDB настроена
   - Миграции созданы
   - Таблицы: `telemetry_samples`, `telemetry_last`, `commands`, `alerts`, `nodes`, `zones`, etc.

### Критические проблемы

1. **Двойная запись телеметрии** ❌
   - Laravel (`PythonIngestController::telemetry`) **пишет напрямую** в `telemetry_samples` и `telemetry_last`
   - `history-logger` тоже пишет эти данные
   - **Нарушение принципа единственной точки записи**

2. **Laravel обновляет статусы команд** ❌
   - `PythonIngestController::commandAck` напрямую меняет `commands.status`
   - По плану это должна делать только Python-часть

3. **Device Registry** ⚠️
   - Функционал частично в Laravel (`NodeService`, `DeviceNode`)
   - Отдельный сервис `device-registry` существует, но не используется
   - Нет поля `validated` в таблице `nodes`

4. **Digital Twin** ⚠️
   - Сервис существует и реализован
   - **НЕ добавлен в `docker-compose.dev.yml`**
   - Нет интеграции в Laravel (нет `DigitalTwinClient`, нет `SimulationController`)

5. **telemetry_last без node_id в уникальном ключе** ❌
   - Текущий primary key: `(zone_id, metric_type)`
   - По плану должен быть: `(zone_id, node_id, metric_type)`
   - **Нельзя хранить телеметрию от нескольких нод одной зоны**

6. **Нет стандартизации metric_type** ❌
   - Нет Enum в Python (`common/metrics.py`)
   - Нет Enum в Laravel (`app/Enums/MetricType.php`)
   - Используются "магические строки"

7. **Alerts не соответствуют плану** ⚠️
   - Нет поля `source` (`biz` vs `infra`)
   - Нет поля `code` (есть только `type`)
   - Нет структурированных кодов (`biz_no_flow`, `biz_overcurrent`, etc.)

8. **api-gateway и device-registry в docker-compose** ⚠️
   - Сервисы не используются, но могут быть упомянуты в документации

---

## План рефакторинга по приоритетам

### Фаза 1: Критические исправления (неделя 1)

#### 1.1. Убрать двойную запись телеметрии

**Задача:** Laravel перестаёт писать телеметрию напрямую, проксирует в `history-logger`.

**Действия:**

1. **Создать REST API в `history-logger`**:
   ```python
   # backend/services/history-logger/main.py
   @app.post("/ingest/telemetry")
   async def ingest_telemetry(req: IngestRequest):
       samples = [TelemetrySampleModel(**s) for s in req.samples]
       await process_telemetry_batch(samples)
       return {"status": "ok", "count": len(samples)}
   ```

2. **Создать общий модуль `common/telemetry.py`**:
   ```python
   class TelemetrySampleModel(BaseModel):
       node_uid: str
       zone_uid: str | None = None
       metric_type: str
       value: float
       ts: datetime
       raw: dict | None = None
   
   async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
       # 1. По node_uid/zone_uid находим node_id, zone_id
       # 2. Проверяем validated
       # 3. Нормализуем metric_type
       # 4. Пишем в telemetry_samples
       # 5. Обновляем telemetry_last
   ```

3. **Использовать в `history-logger`**:
   - MQTT-подписчик вызывает `process_telemetry_batch`
   - HTTP-эндпоинт тоже вызывает `process_telemetry_batch`

4. **Изменить `PythonIngestController::telemetry`**:
   ```php
   public function telemetry(Request $request) {
       $this->ensureToken($request);
       $data = $request->validate([...]);
       
       // Проксируем в history-logger
       Http::post(
           config('services.history_logger.url') . '/ingest/telemetry',
           ['samples' => [$data]]
       );
       
       return Response::json(['status' => 'ok']);
   }
   ```

**Критерии приёмки:**
- ✅ Laravel не пишет в `telemetry_samples`/`telemetry_last`
- ✅ Вся телеметрия идёт через `history-logger`
- ✅ Тесты проходят

---

#### 1.2. Исправить primary key в `telemetry_last`

**Задача:** Добавить `node_id` в уникальный ключ.

**Действия:**

1. **Создать миграцию**:
   ```php
   // database/migrations/XXXX_add_node_id_to_telemetry_last_pk.php
   Schema::table('telemetry_last', function (Blueprint $table) {
       // Удалить старый primary key
       $table->dropPrimary(['zone_id', 'metric_type']);
       
       // Добавить новый (если node_id nullable, нужно обработать NULL)
       $table->primary(['zone_id', 'node_id', 'metric_type'], 'telemetry_last_pk');
   });
   ```

   **ВАЖНО:** Если `node_id` nullable, нужно:
   - Либо сделать его NOT NULL
   - Либо использовать частичный индекс: `UNIQUE (zone_id, COALESCE(node_id, -1), metric_type)`
   - Либо хранить `node_id` как NOT NULL с default значением (но это не рекомендуется)

2. **Обновить `common/db.py::upsert_telemetry_last`**:
   ```python
   async def upsert_telemetry_last(
       zone_id: int, 
       node_id: Optional[int], 
       metric_type: str, 
       channel: Optional[str], 
       value: Optional[float]
   ):
       await execute(
           """
           INSERT INTO telemetry_last (zone_id, node_id, metric_type, channel, value, updated_at)
           VALUES ($1, $2, $3, $4, $5, NOW())
           ON CONFLICT (zone_id, COALESCE(node_id, -1), metric_type)
           DO UPDATE SET channel = EXCLUDED.channel, value = EXCLUDED.value, updated_at = NOW()
           """,
           zone_id, node_id or -1, metric_type, channel, value
       )
   ```

3. **Обновить `history-logger`** для передачи `node_id`

**Критерии приёмки:**
- ✅ Primary key: `(zone_id, node_id, metric_type)`
- ✅ Можно хранить телеметрию от разных нод одной зоны
- ✅ Миграция применяется без ошибок

---

#### 1.3. Laravel не обновляет статусы команд

**Задача:** Статусы `commands.status` меняет только Python.

**Действия:**

1. **Убрать логику из `PythonIngestController::commandAck`**:
   ```php
   public function commandAck(Request $request) {
       $this->ensureToken($request);
       // Удалить код, который обновляет commands.status
       // Возвращать только подтверждение получения
       return Response::json(['status' => 'ok']);
   }
   ```

2. **Убедиться, что `history-logger` обрабатывает `command_response`**:
   - Проверить `handle_command_response` в `history-logger/main.py`
   - Убедиться, что вызывается `mark_command_ack` / `mark_command_failed`

3. **Добавить проверку в Laravel-модели**:
   ```php
   // app/Models/Command.php
   protected $fillable = [..., 'status']; // Оставить для создания, но не обновлять из Laravel
   
   // В контроллерах запретить прямое обновление status
   ```

**Критерии приёмки:**
- ✅ Laravel не обновляет `commands.status`
- ✅ Только Python (`history-logger`, `common/commands.py`) обновляет статусы
- ✅ Тесты проходят

---

### Фаза 2: Стандартизация и улучшения (неделя 2)

#### 2.1. Единый словарь metric_type

**Задача:** Стандартизировать типы метрик.

**Действия:**

1. **Создать `backend/services/common/metrics.py`**:
   ```python
   from enum import Enum
   
   class Metric(str, Enum):
       PH = "ph"
       EC = "ec"
       TEMP_AIR = "temp_air"
       TEMP_WATER = "temp_water"
       HUMIDITY = "humidity"
       CO2 = "co2"
       LUX = "lux"
       WATER_LEVEL = "water_level"
       FLOW_RATE = "flow_rate"
       PUMP_CURRENT = "pump_current"
   
   CANONICAL_METRICS = {m.value: m for m in Metric}
   
   class UnknownMetricError(Exception):
       pass
   
   def normalize_metric_type(raw: str) -> str:
       key = raw.strip().lower()
       if key in CANONICAL_METRICS:
           return CANONICAL_METRICS[key].value
       raise UnknownMetricError(f"Unknown metric type: {raw}")
   ```

2. **Использовать в `common/telemetry.py`**:
   ```python
   from common.metrics import normalize_metric_type, UnknownMetricError
   
   async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
       for sample in samples:
           try:
               normalized = normalize_metric_type(sample.metric_type)
           except UnknownMetricError as e:
               # Логируем и пропускаем
               continue
           # ...
   ```

3. **Создать `app/Enums/MetricType.php`**:
   ```php
   enum MetricType: string
   {
       case PH = 'ph';
       case EC = 'ec';
       case TEMP_AIR = 'temp_air';
       case TEMP_WATER = 'temp_water';
       case HUMIDITY = 'humidity';
       case CO2 = 'co2';
       case LUX = 'lux';
       case WATER_LEVEL = 'water_level';
       case FLOW_RATE = 'flow_rate';
       case PUMP_CURRENT = 'pump_current';
   }
   ```

4. **Использовать в Laravel-моделях и валидации**

**Критерии приёмки:**
- ✅ Python использует только значения из Enum
- ✅ Laravel валидирует через Enum
- ✅ Неизвестные метрики логируются и игнорируются

---

#### 2.2. Device Registry в Laravel

**Задача:** Расширить Laravel для полной реализации device-registry.

**Действия:**

1. **Добавить поля в таблицу `nodes`**:
   ```php
   // migration
   Schema::table('nodes', function (Blueprint $table) {
       $table->boolean('validated')->default(false);
       $table->timestamp('first_seen_at')->nullable();
       $table->string('hardware_revision')->nullable();
       // fw_version уже есть
   });
   ```

2. **Создать `NodeRegistryService`**:
   ```php
   // app/Services/NodeRegistryService.php
   class NodeRegistryService {
       public function registerNode(
           string $nodeUid, 
           ?string $zoneUid, 
           array $attributes = []
       ): DeviceNode {
           $node = DeviceNode::firstOrNew(['uid' => $nodeUid]);
           
           if ($zoneUid) {
               $zone = Zone::where('uid', $zoneUid)->first();
               if ($zone) {
                   $node->zone_id = $zone->id;
               }
           }
           
           $node->firmware_version = $attributes['firmware_version'] ?? $node->firmware_version;
           $node->hardware_revision = $attributes['hardware_revision'] ?? $node->hardware_revision;
           
           if (!$node->first_seen_at) {
               $node->first_seen_at = now();
           }
           
           $node->validated = true;
           $node->save();
           
           return $node;
       }
   }
   ```

3. **Создать API-эндпоинт**:
   ```php
   // routes/api.php
   Route::post('/nodes/register', [NodeController::class, 'register']);
   
   // NodeController::register
   public function register(Request $request) {
       $data = $request->validate([
           'node_uid' => 'required|string',
           'zone_uid' => 'nullable|string',
           'firmware_version' => 'nullable|string',
           'hardware_revision' => 'nullable|string',
       ]);
       
       $node = $this->registryService->registerNode(
           $data['node_uid'],
           $data['zone_uid'] ?? null,
           $data
       );
       
       return new NodeResource($node);
   }
   ```

4. **Обновить `process_telemetry_batch`** для проверки `validated`:
   ```python
   async def process_telemetry_batch(samples: list[TelemetrySampleModel]):
       for sample in samples:
           # Проверяем, что нода зарегистрирована и validated
           node = await fetch_one(
               "SELECT id, validated FROM nodes WHERE uid=$1",
               sample.node_uid
           )
           if not node:
               # Логируем unknown node, игнорируем телеметрию
               continue
           if not node['validated']:
               # Логируем unvalidated node, игнорируем телеметрию
               continue
           # ...
   ```

5. **Обновить `backend/services/api-gateway` и `device-registry`**:
   - Добавить README с пометкой `LEGACY / NOT USED`
   - Удалить из `docker-compose.dev.yml` (если есть)

**Критерии приёмки:**
- ✅ Таблица `nodes` имеет поля `validated`, `first_seen_at`, `hardware_revision`
- ✅ `NodeRegistryService` реализован
- ✅ API `/api/nodes/register` работает
- ✅ Телеметрия от невалидированных нод игнорируется

---

#### 2.3. Alerts: source + code

**Задача:** Добавить структурированные алерты.

**Действия:**

1. **Создать миграцию**:
   ```php
   Schema::table('alerts', function (Blueprint $table) {
       $table->string('source')->default('biz'); // biz / infra
       $table->string('code')->nullable(); // biz_no_flow, biz_overcurrent, etc.
       // type остаётся для обратной совместимости
   });
   ```

2. **Создать Enum в Python**:
   ```python
   # common/alerts.py
   class AlertSource(str, Enum):
       BIZ = "biz"
       INFRA = "infra"
   
   class AlertCode(str, Enum):
       # Бизнес
       BIZ_NO_FLOW = "biz_no_flow"
       BIZ_OVERCURRENT = "biz_overcurrent"
       BIZ_DRY_RUN = "biz_dry_run"
       BIZ_PUMP_STUCK_ON = "biz_pump_stuck_on"
       BIZ_HIGH_PH = "biz_high_ph"
       BIZ_LOW_PH = "biz_low_ph"
       BIZ_HIGH_EC = "biz_high_ec"
       BIZ_LOW_EC = "biz_low_ec"
       
       # Инфраструктура
       INFRA_MQTT_DOWN = "infra_mqtt_down"
       INFRA_DB_UNREACHABLE = "infra_db_unreachable"
       INFRA_SERVICE_DOWN = "infra_service_down"
   ```

3. **Обновить функции создания алертов**:
   ```python
   async def create_alert(
       zone_id: Optional[int],
       source: str,  # biz / infra
       code: str,    # biz_no_flow, etc.
       type: str,    # человекочитаемый текст
       details: Optional[Dict[str, Any]] = None
   ):
       await execute(
           """
           INSERT INTO alerts (zone_id, source, code, type, details, status, created_at)
           VALUES ($1, $2, $3, $4, $5, 'ACTIVE', NOW())
           """,
           zone_id, source, code, type, json.dumps(details) if details else None
       )
   ```

4. **Обновить Laravel-модель**:
   ```php
   class Alert extends Model {
       protected $fillable = [..., 'source', 'code'];
   }
   ```

**Критерии приёмки:**
- ✅ Таблица `alerts` имеет поля `source` и `code`
- ✅ Все новые алерты создаются с `source` и `code`
- ✅ Обратная совместимость: старые алерты работают

---

### Фаза 3: Интеграция Digital Twin (неделя 3)

#### 3.1. Добавить digital-twin в docker-compose

**Действия:**

1. **Добавить сервис в `docker-compose.dev.yml`**:
   ```yaml
   digital-twin:
     build:
       context: ./services
       dockerfile: digital-twin/Dockerfile
     environment:
       - PG_HOST=db
       - PG_USER=hydro
       - PG_PASS=hydro
       - PG_DB=hydro_dev
     depends_on:
       - db
     ports:
       - "8003:8003"
       - "9403:9403"  # Prometheus
   ```

2. **Проверить работоспособность**:
   ```bash
   curl http://localhost:8003/health
   ```

---

#### 3.2. Создать DigitalTwinClient в Laravel

**Действия:**

1. **Создать сервис**:
   ```php
   // app/Services/DigitalTwinClient.php
   class DigitalTwinClient {
       public function __construct(
           private HttpClient $http
       ) {
       }
       
       public function simulateZone(int $zoneId, array $params): array {
           $response = $this->http->post(
               config('services.digital_twin.url') . '/simulate/zone',
               [
                   'zone_id' => $zoneId,
                   'duration_hours' => $params['duration_hours'] ?? 72,
                   'step_minutes' => $params['step_minutes'] ?? 10,
                   'scenario' => $params['scenario'] ?? [],
               ]
           );
           
           return $response->json();
       }
   }
   ```

2. **Зарегистрировать в `config/services.php`**:
   ```php
   'digital_twin' => [
       'url' => env('DIGITAL_TWIN_URL', 'http://digital-twin:8003'),
   ],
   ```

3. **Создать `SimulationController`**:
   ```php
   // app/Http/Controllers/SimulationController.php
   class SimulationController extends Controller {
       public function __construct(
           private DigitalTwinClient $client
       ) {
       }
       
       public function simulateZone(Request $request, Zone $zone) {
           $data = $request->validate([
               'duration_hours' => 'integer|min:1|max:720',
               'step_minutes' => 'integer|min:1|max:60',
               'initial_state' => 'array',
               'recipe_id' => 'nullable|exists:recipes,id',
           ]);
           
           $scenario = [
               'recipe_id' => $data['recipe_id'] ?? $zone->active_recipe_id,
               'initial_state' => $data['initial_state'] ?? [],
           ];
           
           $result = $this->client->simulateZone($zone->id, [
               'duration_hours' => $data['duration_hours'] ?? 72,
               'step_minutes' => $data['step_minutes'] ?? 10,
               'scenario' => $scenario,
           ]);
           
           return response()->json($result);
       }
   }
   ```

4. **Добавить роут**:
   ```php
   Route::post('/zones/{zone}/simulate', [SimulationController::class, 'simulateZone']);
   ```

**Критерии приёмки:**
- ✅ `digital-twin` работает в docker-compose
- ✅ Laravel может вызвать симуляцию
- ✅ API `/api/zones/{id}/simulate` работает

---

### Фаза 4: Дополнительные улучшения (неделя 4+)

#### 4.1. Модель воды: замкнутый контур и смена воды

**Задача:** Добавить поддержку циркуляции и плановой смены воды.

**Действия:**

1. **Добавить поля в `zones.settings`**:
   ```json
   {
     "water_cycle": {
       "mode": "RECIRCULATING",
       "recirc": {
         "enabled": true,
         "schedule": [{"from": "00:00", "to": "23:59", "duty_cycle": 0.5}],
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
   }
   ```

2. **Добавить состояние зоны**:
   ```php
   // migration
   Schema::table('zones', function (Blueprint $table) {
       $table->string('water_state')->default('NORMAL_RECIRC');
       // NORMAL_RECIRC / WATER_CHANGE_DRAIN / WATER_CHANGE_FILL / WATER_CHANGE_STABILIZE
       $table->timestamp('solution_started_at')->nullable();
   });
   ```

3. **Реализовать логику в `automation-engine`**:
   - Функция `tick_recirculation(zone)`
   - Функция `check_water_change_required(zone)`
   - Функция `execute_water_change(zone)`

4. **Интегрировать в `scheduler`**:
   - Периодическая проверка необходимости смены воды
   - Переход в состояние `WATER_CHANGE_DRAIN`

**Критерии приёмки:**
- ✅ Настройки циркуляции и смены воды хранятся в БД
- ✅ Автоматика управляет циркуляцией с учётом NC-насоса
- ✅ Автоматика запускает смену воды по расписанию/условиям

---

#### 4.2. Безопасность насосов

**Задача:** Реализовать проверки no_flow, overcurrent, dry_run, pump_stuck_on.

**Действия:**

1. **Создать `common/pump_safety.py`**:
   ```python
   async def check_no_flow(zone_id, pump_channel, cmd_id, telemetry_window):
       # Проверка по flow_rate или water_level
       pass
   
   async def check_dry_run(zone_id, min_water_level):
       water_level = await get_latest_metric(zone_id, "water_level")
       if water_level < min_water_level:
           await create_alert(zone_id, 'biz', 'biz_dry_run', 'Dry run protection', {...})
           return False
       return True
   
   async def check_pump_stuck_on(zone_id, pump_channel):
       # Проверка: желаемое состояние OFF, но ток/flow > порога
       pass
   ```

2. **Обновить `mqtt-bridge` для обработки overcurrent**:
   - При получении `command_response` с `error_code: "overcurrent"` создавать alert

3. **Обновить `automation-engine`**:
   - Перед запуском насоса вызывать `can_run_pump(zone_id, pump_channel)`
   - Проверять активные alerts с критическими кодами

**Критерии приёмки:**
- ✅ Проверки реализованы
- ✅ Алерты создаются при нарушении
- ✅ Насосы не запускаются при критических условиях

---

#### 4.3. Новый сервис telemetry-aggregator

**Задача:** Агрегировать телеметрию в `telemetry_agg_1m`, `telemetry_agg_1h`, `telemetry_daily`.

**Действия:**

1. **Создать структуру сервиса**:
   ```
   backend/services/telemetry-aggregator/
   ├── main.py
   ├── requirements.txt
   ├── Dockerfile
   └── README.md
   ```

2. **Создать таблицу `aggregator_state`**:
   ```sql
   CREATE TABLE aggregator_state (
       id SERIAL PRIMARY KEY,
       aggregation_type VARCHAR(32) UNIQUE,  -- '1m', '1h', 'daily'
       last_ts TIMESTAMP,
       updated_at TIMESTAMP
   );
   ```

3. **Реализовать агрегацию**:
   ```python
   async def aggregate_1m():
       last_ts = await get_last_ts('1m')
       await execute("""
           INSERT INTO telemetry_agg_1m (zone_id, node_id, metric_type, ...)
           SELECT zone_id, node_id, metric_type, 
                  time_bucket('1 minute', ts) as bucket,
                  AVG(value) as avg_value, ...
           FROM telemetry_samples
           WHERE ts > $1
           GROUP BY zone_id, node_id, metric_type, bucket
       """, last_ts)
   ```

4. **Добавить в docker-compose**

**Критерии приёмки:**
- ✅ Сервис агрегирует телеметрию
- ✅ Агрегаты сохраняются в БД
- ✅ Сервис работает периодически

---

## Чек-лист рефакторинга

### Фаза 1: Критические исправления ✅
- [x] Создать `common/telemetry.py` с `process_telemetry_batch`
- [x] Добавить HTTP API в `history-logger` для ингеста
- [x] Изменить `PythonIngestController::telemetry` на проксирование
- [x] Убрать запись телеметрии из Laravel
- [x] Исправить primary key в `telemetry_last` (добавить `node_id`)
- [x] Обновить `upsert_telemetry_last` для нового ключа
- [x] Убрать обновление `commands.status` из Laravel
- [x] Убедиться, что только Python обновляет статусы команд

### Фаза 2: Стандартизация ✅
- [x] Создать `common/metrics.py` с Enum
- [x] Реализовать `normalize_metric_type`
- [x] Использовать нормализацию в `process_telemetry_batch`
- [x] Создать `app/Enums/MetricType.php`
- [x] Использовать Enum в Laravel-валидации
- [x] Добавить поля в таблицу `nodes` (validated, first_seen_at, hardware_revision)
- [x] Создать `NodeRegistryService`
- [x] Создать API `/api/nodes/register`
- [x] Обновить `process_telemetry_batch` для проверки validated
- [x] Добавить поля `source` и `code` в таблицу `alerts`
- [x] Создать `common/alerts.py` с кодами
- [x] Обновить функции создания алертов

### Фаза 3: Digital Twin ✅
- [x] Добавить `digital-twin` в docker-compose.dev.yml
- [x] Создать `DigitalTwinClient` в Laravel
- [x] Создать `SimulationController`
- [x] Добавить роут `/api/zones/{id}/simulate`
- [x] Протестировать интеграцию
- [x] Добавить UI для симуляции (ZoneSimulationModal.vue)

### Фаза 4: Дополнительные улучшения ✅
- [x] Добавить поля water_cycle в zones.settings
- [x] Добавить water_state в таблицу zones
- [x] Реализовать логику циркуляции в automation-engine
- [x] Реализовать логику смены воды в scheduler
- [x] Создать `common/pump_safety.py`
- [x] Реализовать проверки безопасности насосов
- [x] Создать сервис `telemetry-aggregator`
- [x] Реализовать агрегацию телеметрии
- [x] Исправить баги: дефолтные значения в `get_zone_water_cycle_config`, использование констант в `scheduler`, fallback для `aggregate_1m`, конфигурация интервала агрегации

### Дополнительные доработки (из аудита 01_SYSTEM) ✅
- [x] Реализовать жизненный цикл узлов (lifecycle_state, hardware_id)
- [x] Добавить Enum `NodeLifecycleState` в Laravel
- [x] Создать `NodeLifecycleService` для управления переходами
- [x] Реализовать обработку `node_hello` в history-logger
- [x] Интегрировать `node_hello` с Laravel API регистрации
- [x] Создать `NodeConfigService` для генерации NodeConfig
- [x] Реализовать автоматическую синхронизацию NodeConfig через Events
- [x] Добавить обработку heartbeat в history-logger
- [x] Добавить поля heartbeat в таблицу `nodes` (last_heartbeat_at, uptime_seconds, free_heap_bytes, rssi)
- [x] Создать `NodeSwapService` для замены узлов
- [x] Добавить API endpoint `/api/nodes/{node}/swap`

---

## Риски и митигация

### Риск 1: Потеря данных при изменении primary key
**Митигация:**
- Создать backup перед миграцией
- Использовать транзакции
- Протестировать на dev-окружении

### Риск 2: Несовместимость с текущими данными
**Митигация:**
- Миграции должны быть обратно-совместимыми
- Добавить default значения
- Постепенное обновление

### Риск 3: Проблемы с производительностью при проксировании
**Митигация:**
- Использовать async HTTP-клиент
- Батчинг запросов
- Мониторинг latency

---

## Документация

После завершения каждой фазы необходимо обновить:
- `doc_ai/04_BACKEND_CORE/BACKEND_REFACTOR_PLAN.md` (отметить выполненные пункты)
- `doc_ai/IMPLEMENTATION_STATUS.md` (обновить статусы)
- `backend/README.md` (обновить описание архитектуры)

---

## Заключение

План рефакторинга разбит на 4 фазы по приоритетам:
1. **Фаза 1** — критические исправления (единственная точка записи, корректная схема БД)
2. **Фаза 2** — стандартизация (метрики, device-registry, алерты)
3. **Фаза 3** — интеграция Digital Twin
4. **Фаза 4** — дополнительные улучшения (модель воды, безопасность, агрегация)

Каждая фаза может быть выполнена независимо, но рекомендуется следовать порядку для минимизации рисков.

