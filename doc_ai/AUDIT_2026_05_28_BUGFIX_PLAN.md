# AUDIT_2026_05_28_BUGFIX_PLAN.md
# План багфиксов по результатам code-аудита 2026-05-28

**Дата:** 2026-05-28
**Версия:** 1.2 (последнее обновление 2026-05-28: финализация S1-S4, детализация S5)
**Скоуп:** Все 6 слоёв проекта (AE3 / Python services / Laravel / Frontend / Firmware / DB+Ops)
**Объём аудита:** 444 находки (~46 critical, ~167 high, ~154 medium, ~77 low)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## Принципы

1. **Поэтапная доставка.** Большие рефакторинги (god-классы, унификация publish path) — отдельный трек; этот план фокусируется на исправлении багов и снижении рисков.
2. **Тесты как gate.** После каждого этапа — прогон релевантного suite. Регрессия = блокер для merge этапа.
3. **Backward-compat по контрактам.** Изменения protected pipeline `ESP32 → MQTT → Python → PG → Laravel → Vue` запрещены. Все security-правки делаются **аддитивно** (новые требования авторизации с feature-flag для grace period, если нужно).
4. **Один этап — один (или несколько узких) коммитов.** Стиль: `fix(<scope>): ...` или `refactor(<scope>): ...`.

---

## Карта приоритетов и прогресс

| Этап | Тема | Объём | Срочность | Риск | Статус | Коммит |
|------|------|-------|-----------|------|--------|--------|
| **S1** | Security fast-track | 18 файлов | **CRITICAL** | низкий | ✅ **DONE** (7/7) | `60ad6323` |
| **S2** | Code-bug фиксы | 9 файлов | **HIGH** | средний | ✅ **DONE** (4/5; S2.4 → B11) | `c0433dad` |
| **S3** | Timescale compression policies | 1 миграция | **HIGH** | низкий | ✅ **DONE** | `8cc502c2` |
| **S4** | WS dedup на frontend | 3 файла | **HIGH** | средний | ✅ **DONE** (race-fix; рефакторинг отложен) | `ec2aa25a` |
| **S5** | Архитектурный рефакторинг | большой | medium | высокий | 🟡 **PLANNED** (5 sub-tasks, многонедельный track) | — |

### Сводка по выполненному (S1-S4)

**Объём:** 31 файл (включая 1 миграцию и 1 doc), коммиты с защищённым полным test suite.

**Bugs fixed:**
- 3 critical security gaps (DLQ/internal/metrics, digital-twin, node-sim — все open RCE-equivalent endpoints закрыты);
- 2 timing leak'а (Bearer-сравнение → `hmac.compare_digest`);
- 1 default secret bypass (NODE_DEFAULT_SECRET → fail-closed в production);
- 2 exception leak'а (raw `$e->getMessage()` в JSON убран);
- 1 `env()` runtime bug (`config:cache`-incompatible);
- 1 cache DoS (`Cache::flush()` → targeted invalidation);
- 1 firmware MQTT contract bug (pump_node telemetry до time-sync);
- 1 AE3 race в `recover_waiting_command` (opt-in owner guard);
- 4 frontend `axios` bypass (services/api boundary);
- 1 Timescale compression gap (telemetry_samples + hypertable восстановлен);
- 1 WS race condition в `echoClient.teardownEcho` (async cleanup → sync через event);

**Bugs deferred to backlog:**
- B11: HL httpx pool reuse (8 тестов с `httpx.AsyncClient` mocking требуется обновить).

**Tests:** все слои зелёные после каждого этапа:
- Laravel: 1009 (5117-5177 assertions)
- AE3: 1520
- HL: 492
- mqtt-bridge: 293
- Vitest: 1493 (1 skipped)
- Pint/ESLint/typecheck: clean

---

## Этап S1 — Security fast-track ✅ DONE

> **Статус:** выполнено 2026-05-28, коммит `60ad6323`. Все 7 sub-tasks
> закрыты. См. полный CHANGELOG в commit message.

### Цель

Закрыть все critical-находки безопасности: открытые operational endpoints, timing leaks, secrets-default, утечки exception-сообщений.

### S1.1 — Auth на `history-logger` DLQ + internal metrics

**Файлы:**
- `backend/services/history-logger/system_routes.py:161–402`

**Проблема:** `GET/POST/DELETE /api/dlq/alerts/*`, `/api/dlq/status-updates/*`, `/api/dlq/metrics`, `POST /internal/metrics/*` доступны без аутентификации, порт 9300 проброшен на хост.

**План:**
- Применить существующий `require_token` (auth dependency, см. `history-logger/auth.py`) ко всем endpoints в `system_routes.py` группы DLQ и internal-metrics.
- Health endpoint (`GET /health`) **оставить без auth** (Prometheus/Docker healthcheck).
- Добавить негативные тесты: вызов без токена → `401`.

**Acceptance:**
- `pytest backend/services/history-logger/tests/test_dlq_routes.py` зелёный.
- Curl без `Authorization: Bearer …` на `/api/dlq/alerts` возвращает 401.

### S1.2 — Auth на `digital-twin` operational endpoints

**Файлы:**
- `backend/services/digital-twin/main.py:803–1030+`

**Проблема:** `/simulate/zone`, `/simulations/live/start|stop`, `/calibrate/zone/{id}` без auth; live-start дёргает node-sim-manager и публикует в MQTT (порт 8003 проброшен).

**План:**
- Ввести FastAPI dependency `require_dt_token` по аналогии с HL (через `DIGITAL_TWIN_API_TOKEN` ENV).
- Применить к всем mutating endpoints.
- `/health` оставить без auth.

**Acceptance:**
- Простой smoke-тест внутри контейнера.

### S1.3 — Auth на `node-sim-manager`

**Файлы:**
- `backend/services/node-sim-manager/main.py:143–212`

**Проблема:** `/sessions/start/stop/{id}` без auth; запускает `subprocess.Popen` от произвольного YAML payload — фактически RCE для атакующего внутри сети.

**План:**
- Дополнить dependency `require_token` (ENV `NODE_SIM_MANAGER_TOKEN`, уже определён в `config/services.php`).
- Применить ко всем `/sessions/*`.
- Health/list endpoints без auth (если уже используются для observer).

**Acceptance:**
- Тест: curl без токена → 401.
- Существующий Laravel-клиент `App\Services\NodeSimManagerClient` уже передаёт токен (см. `config/services.php:97`) → совместимо.

### S1.4 — Timing-safe сравнение токенов

**Файлы:**
- `backend/services/history-logger/auth.py:45,62`
- `backend/services/mqtt-bridge/main.py:152,168`
- Любые другие найденные `!=` для секретов

**Проблема:** Сравнение через `!=` — теоретическая уязвимость timing attack.

**План:**
- Заменить `provided != expected` на `not hmac.compare_digest(provided, expected)`.
- Обернуть `secrets.compare_digest` если строка может быть None.

**Acceptance:**
- `grep -rn "token.*!=" backend/services/ | grep -v test` → пусто.

### S1.5 — Убрать `NODE_DEFAULT_SECRET` (fail-closed)

**Файлы:**
- `backend/services/common/env.py:48`
- `backend/services/history-logger/commands/validation.py:33–42`

**Проблема:** Дефолтный секрет `"hydro-default-secret-key-2025"` встраивается в NodeConfig при publish, если node_secret не задан. Эксплуатируется любым клиентом, знающим default.

**План:**
- Снять дефолт (`NODE_DEFAULT_SECRET: Optional[str] = None`).
- В `commands/validation.py` при отсутствии `node_secret` для конкретной ноды **отказывать в публикации** с кодом `node_secret_missing` (фейл-клозед).
- Логировать ошибку с `node_uid`, не светить секрет в логе.

**Acceptance:**
- Прогон HL тестов; должны быть новые сценарии "publish без node_secret → 422".

### S1.6 — Убрать exception messages из JSON response (Laravel)

**Файлы:**
- `backend/laravel/app/Http/Controllers/ZoneCommandController.php:210–226`
- `backend/laravel/app/Http/Controllers/PythonIngestController.php:718–721`
- Любые другие `'message' => $e->getMessage()` / `'details' => $e->getMessage()`

**Проблема:** Stack trace или внутренние пути могут утечь в response.

**План:**
- Заменить exception message на статический pretty-message + опциональный `error_code`.
- Лог exception с trace через `Log::error()` остаётся.
- В response — только safe-to-show строка (`'Internal error during command publish'`) и/или `code` из catalog.

**Acceptance:**
- PHPUnit: existing tests должны продолжать работать (текст ошибки в response может поменяться, но статус-коды/структура — нет).

### S1.7 — `env()` из runtime → `config()`

**Файлы:**
- `backend/laravel/app/Http/Middleware/VerifyPythonServiceToken.php:30`
- `backend/laravel/bootstrap/app.php:46–49`
- `backend/laravel/routes/api.php:60–64`
- `backend/laravel/app/Http/Controllers/PipelineHealthController.php:46,64`
- `backend/laravel/app/Http/Controllers/SystemController.php:79,126,189`
- `backend/laravel/app/Console/Commands/ProcessCommandTimeouts.php:35`
- `backend/laravel/app/Services/JsonSchemaValidator.php:52`
- `backend/laravel/app/Console/Commands/FullBackupCommand.php:33`
- `backend/laravel/app/Console/Commands/BackupListCommand.php:17`

**Проблема:** `env()` вне config-файлов ломает `php artisan config:cache` в production — middleware/контроллер будет видеть `null`.

**План:**
- Добавить ключи в `config/services.php` или новый `config/automation.php`.
- Заменить `env('FOO')` на `config('services.foo')` / `config('automation.foo')`.

**Acceptance:**
- `grep -rn "env(" backend/laravel/app/ backend/laravel/bootstrap/ backend/laravel/routes/` — только config-файлы.
- `php artisan config:cache && php artisan test` — зелёный.

### S1 — Definition of Done

- [ ] Все 7 sub-tasks (S1.1–S1.7) выполнены.
- [ ] `make test-laravel`, `make test-hl`, `make test-mqttb`, `make test-fb` — зелёные.
- [ ] `npm run lint`, `npm run typecheck`, `vendor/bin/pint --test` — без новых ошибок.
- [ ] Коммит: `fix(security): close open operational endpoints, secrets, env-runtime`.

---

## Этап S2 — Code-bug фиксы ✅ DONE (4/5)

> **Статус:** выполнено 2026-05-28, коммит `c0433dad`. 4 из 5 sub-tasks
> закрыты; S2.4 (HL httpx pool reuse) отложен в backlog B11 — попытка
> сломала 8 production тестов с `httpx.AsyncClient` mocking.

### S2.1 — `Cache::flush()` без tags

**Файл:** `backend/laravel/app/Services/NodeService.php:292,348`

**Проблема:** Полный flush кэша при обновлении ноды → DoS на shared cache.

**План:**
- Использовать `Cache::tags(['nodes', "zone:$zoneId"])->flush()` если драйвер поддерживает.
- Если file driver (без tags) — таргетированное `Cache::forget("zones_list_$userId")` для конкретных ключей.

### S2.2 — `pump_node` time-sync gating

**Файл:** `firmware/nodes/pump_node/main/pump_node_tasks.c:167,211`

**Проблема:** Публикует telemetry с `ts` **до** time-sync (нарушает MQTT contract §4.2).

**План:**
- Добавить `if (!node_utils_is_time_synced()) { return; }` перед публикацией telemetry.
- Совместимо с другими нодами (паттерн уже используется).

### S2.3 — AE3 `mark_publish_accepted` ↔ `recover_waiting_command` race

**Файлы:** `backend/services/automation-engine/ae3lite/infrastructure/repositories/automation_task_repository.py:507–521`, `gateways/sequential_command_gateway.py`

**Проблема:** `recover_waiting_command` не проверяет `claimed_by`/`owner` → возможен race при concurrent worker restart.

**План:**
- Добавить параметр `owner` в `recover_waiting_command`, проверять `claimed_by = $owner` в SQL.

### S2.4 — HL: новый `httpx.AsyncClient` на каждый запрос

**Статус:** **отложено в backlog B11.** Попытка перевода в Stage 2 сломала 8
production тестов, которые мокают `httpx.AsyncClient` через context manager.
Требуется параллельное обновление тестов перед merge.

**Файлы:**
- `backend/services/history-logger/handlers/node_hello.py:199`
- `backend/services/history-logger/handlers/config_report.py:395`
- `backend/services/digital-twin/main.py:532`

**Проблема:** Создание клиента на каждый запрос — лишние TCP handshakes + утечка connections при exception.

**План:**
- Использовать `http_client_pool` / shared client из lifespan.
- Перед merge: обновить тесты в `test_critical_fixes.py::TestLaravelApiRetry`
  (6 тестов) и `test_format_sync_integration.py` (2 теста).

### S2.5 — `npm run lint:api-boundary` для всех Pages

**Файл:** `backend/laravel/resources/js/Pages/Greenhouses/Climate.vue`, `Components/Infrastructure/ZoneBindingsPanel.vue`

**Проблема:** Прямой `axios.*` мимо `services/api`.

**План:**
- Заменить на `import { api } from '@/services/api'`.
- Расширить `lint:api-boundary` чтобы ловил в Pages/Components, не только в composables.

### S2 — Definition of Done

- [ ] Все 5 sub-tasks выполнены.
- [ ] Тесты зелёные.
- [ ] Коммит: `fix(stability): cache-flush scope, time-sync gating, http pool reuse, ws race`.

---

## Этап S3 — Timescale compression policies ✅ DONE

> **Статус:** выполнено 2026-05-28, коммит `8cc502c2`. Полностью закрыто +
> побочно восстановлен hypertable status у `telemetry_samples` (был потерян
> destructive миграцией `2025_12_25_151719_*`).

### S3.1 — Compression для hypertables

**Миграция:** `2026_05_28_140000_add_compression_policies_for_timeseries.php`

**Таблицы:**
- `telemetry_samples` — retention 90d, compress after 7d
- `telemetry_agg_1h` — retention 365d, compress after 30d
- `commands` — retention 365d, compress after 7d
- `zone_events` — retention 365d, compress after 30d
- `zone_features_5m` — добавить retention (90d) + compress 7d

**План:**
- Использовать `add_compression_policy` через `DB::statement` (Timescale-specific).
- Skip в testing env (как у других hypertable-миграций).
- `$withinTransaction = false`.

**Acceptance:**
- `make migrate` без ошибок.
- В Timescale: `SELECT * FROM timescaledb_information.compression_settings;` показывает 5 строк.

---

## Этап S4 — WS dedup на frontend ✅ DONE (частично; рефакторинг отложен)

> **Статус:** выполнено 2026-05-28, коммит `ec2aa25a`. Реальный bug
> (race в `echoClient.teardownEcho`) исправлен. Полная унификация подписок
> признана acceptable design — refactor отложен (см. ниже).

### S4.1 — Унификация подписок на `hydro.zones.{id}`

**Статус:** **частично выполнено / уточнено.** При детальном анализе оказалось,
что архитектура `subscribeManagedChannelEvents` уже использует **shared
channel pool с ref-counting** (`ws/sharedEchoChannels.ts`,
`ws/managedChannelEvents.ts`) — фактический WebSocket-канал на зону **один**,
несмотря на 5 раздельных listener'ов от разных composables. Каждый listener
выполняет **уникальную** работу (status update vs runtime refresh vs telemetry
batch vs grow cycle reload vs event ledger), поэтому дублирование callbacks —
acceptable design, не bug.

**Что реально исправлено в Stage 4:**

1. **Race condition в `echoClient.teardownEcho()`** (audit critical, файл
   `utils/echoClient.ts:141–197`):
   - Раньше `emitState('disconnected')` выполнялся синхронно, а
     `cleanupWebSocketChannels()` через async dynamic import. В окне между
     ними мог запуститься `scheduleReconnect()` → подключение раньше
     cleanup'а каналов → дубли listener'ов.
   - Fix: `cleanupWebSocketChannels()` теперь вызывается **синхронно**
     через `window.dispatchEvent('echo:teardown')`, на который подписан
     module-level listener в `useWebSocket.ts`. `emitState` идёт **после**
     cleanup'а.
   - То же исправление применено в `catch`-блоке `initEcho` (строка 524).

**Что отложено в backlog (низкий приоритет):**

- Полный рефакторинг подписок через shared event emitter из `useZonePageState`.
  Audit предполагал "6 listeners → 1", но архитектурно текущая модель
  через shared channel пул уже эквивалентна по network cost (один WS-канал
  на зону). Vue-level callbacks остаются разделёнными по доменной
  ответственности, что улучшает testability и diagnostic. Refactor приносит
  marginal benefit при высокой стоимости.

- Дублирующие handler `.EventCreated` + `.App\Events\EventCreated` —
  это alias-handlers для broadcastAs/класс-имени Laravel. Laravel может
  слать оба варианта (см. `ws/channelControlManager.ts:GLOBAL_EVENT_
  CREATED_EVENTS`); удаление одного из них опасно без полного contract test.

**Acceptance (Stage 4):**

- Vitest WS-suite зелёный (194 файлов, 1493 passed).
- Все тесты слоёв проходят (Laravel 1009, AE3 1520, HL 492, Vitest 1493).
- Manual race-test: открыть DevTools → trigger `teardownEcho` →
  `cleanupWebSocketChannels()` вызывается **до** `emitState('disconnected')`
  в том же call-stack (проверено code-review).

---

## Этап S5 — Архитектурный рефакторинг

> **Статус:** 🟡 **PLANNED.** Многонедельный track. Каждый sub-task — отдельный
> PR с обязательным test coverage. Не блокирует bug-fix трек (S1-S4 уже в
> production). Этот раздел структурирован как **детальные ТЗ для ИИ-агента**:
> каждый sub-task содержит контекст, конкретные пути, target architecture,
> acceptance criteria, риски и mitigation.

### Принципы выполнения S5

1. **One sub-task = one PR**: S5.1 не блокирует S5.2 и т.д. Можно идти
   параллельно разными агентами. Зависимости явно указаны ниже.
2. **Test-first**: к каждому sub-task сначала добавляются characterization
   tests на текущее поведение, затем рефакторинг с зелёным suite на каждом
   шаге.
3. **Behavior preservation**: рефакторинг **не меняет** observable
   behavior. Никаких изменений в:
   - MQTT-контракте (`doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`)
   - REST API контракте (`doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`)
   - WebSocket каналах/событиях (`doc_ai/11_WEBSOCKET_ARCHITECTURE.md`)
   - DB schema / migrations
   - Inertia props формате
4. **Atomic intermediate state**: после каждого коммита проект должен
   собираться и тесты должны проходить. Никаких "WIP, не работает" коммитов.
5. **`Compatible-With`** в каждом commit message обязательно.

### Зависимости sub-tasks

```
S5.1 (god-классы) ───┬─→ независим от других, можно делать по 1 файлу
                     │
S5.2 (publish path) ─┴─→ зависит от S5.4 (decouple domain↔infra) — после
                         выноса infra metrics за пределы domain удобнее
                         делать unified publish gateway
                     
S5.3 (Policy) ───────→ независим
S5.4 (domain↔infra) ─→ независим
S5.5 (frontend) ─────→ независим
```

---

### S5.1 — God-классы → splitting

#### S5.1.A — `correction.py` (AE3, 2307 строк)

**Файл:** `backend/services/automation-engine/ae3lite/application/handlers/correction.py`

**Текущее состояние:** Один класс `CorrectionHandler` со всеми correction
sub-routines: `_run_check`, `_run_dose_ec`, `_run_dose_ph`,
`_run_wait_ec`, `_run_wait_ph`, `_apply_observation`, `_handle_no_effect`,
`_check_attempt_limits`, и т.д. 15+ методов >100 строк.

**Target structure:**

```
ae3lite/application/handlers/correction/
├── __init__.py              # re-export `CorrectionHandler` для backward-compat импортов
├── handler.py               # CorrectionHandler façade, делегирует sub-services
├── steps/
│   ├── __init__.py
│   ├── check.py             # _run_check + decision routing (~300 строк)
│   ├── dose_ec.py           # _run_dose_ec + multi-component sequential/parallel (~400 строк)
│   ├── dose_ph.py           # _run_dose_ph (~250 строк)
│   ├── wait_observe.py      # _run_wait_ec, _run_wait_ph, _apply_observation (~350 строк)
│   └── exhaust.py           # _handle_no_effect, _check_attempt_limits, exhaustion paths (~250 строк)
└── policies/
    ├── __init__.py
    ├── limit_policy.py      # CORRECTION_LIMIT_POLICY_APPLIED / ATTEMPT_CAP_IGNORED логика
    └── decision_routing.py  # selectAction (needs_ec / needs_ph_up / needs_ph_down)
```

**Acceptance:**
- Каждый файл ≤ 600 строк.
- Существующие 80+ тестов `test_ae3lite_correction_*.py` зелёные без модификаций (façade сохраняет API).
- Новый файл `test_correction_steps_isolation.py` с unit-тестами на каждый step (без `BaseStageHandler` контекста).
- Существующие импорты `from ae3lite.application.handlers.correction import CorrectionHandler` продолжают работать.

**Риски:** state-leakage между steps (shared `pid_state`, `corr_*` columns).
Mitigation: каждый step получает `task` и `runtime` как явные параметры,
не использует instance state кроме `_repo`/`_gateway`/`_metrics`.

**Оценка:** 3-5 дней.

#### S5.1.B — `base.py` handlers (AE3, 2004 строки)

**Файл:** `backend/services/automation-engine/ae3lite/application/handlers/base.py`

**Текущее:** `BaseStageHandler` + ~25 free functions. Смешивает:
- live-reload checkpoint (`_checkpoint`)
- IRR probe orchestration (`_probe_irr_state`, `_reconcile_recent_emergency_stop`)
- sensor bounds check (`_sensor_value_in_bounds`)
- effective targets (`_effective_ec_target`, `_effective_ph_target`, day/night)
- level monitor proxy

**Target structure:**

```
ae3lite/application/handlers/base/
├── __init__.py              # re-export BaseStageHandler
├── handler.py               # BaseStageHandler base class (только lifecycle + abstract run)
├── checkpoint.py            # _checkpoint (hot-reload runtime config)
├── probe/
│   ├── irr_state.py         # IRR probe + retry/streak limit
│   └── emergency_stop.py    # reconcile_recent_emergency_stop
├── targets/
│   ├── effective.py         # _effective_{ec,ph}_target/min/max
│   ├── day_night.py         # _is_day_now, _day_night_override*
│   └── bounds.py            # _sensor_value_in_bounds, pH/EC sanity ranges
└── monitoring/
    └── level_monitor.py     # proxy на application/level_monitor.py
```

**Acceptance:**
- `BaseStageHandler` ≤ 400 строк.
- Каждый handler stage (`startup.py`, `clean_fill.py`, и т.д.) импортирует
  только нужные helpers, не весь `base.py`.
- `test_ae3lite_handler_base.py` зелёный.

**Оценка:** 2-3 дня.

#### S5.1.C — `execute_task.py` (AE3, 1387 строк)

**Файл:** `backend/services/automation-engine/ae3lite/application/use_cases/execute_task.py`

**Текущее:** `ExecuteTaskUseCase.run()` 311 строк. Смешивает:
- snapshot load + retry
- topology verification (required node types)
- workflow stage execution
- terminal status handling
- timeout + cancel

**Target structure:**

```
ae3lite/application/use_cases/execute_task/
├── __init__.py              # re-export ExecuteTaskUseCase
├── use_case.py              # ExecuteTaskUseCase orchestrator (≤ 400 строк)
├── snapshot_load.py         # load_zone_snapshot_with_retry + ae3_snapshot_retry_scheduled
├── topology_verify.py       # _verify_topology_required_node_types
└── timeout_guard.py         # AE_MAX_TASK_EXECUTION_SEC + fail-safe shutdown
```

**Acceptance:**
- Существующий `test_ae3lite_execute_task.py` (множество кейсов) зелёный.
- Каждый sub-module имеет своё unit-test покрытие.
- Imports across `ae3lite/` не сломаны (façade re-export).

**Оценка:** 2-3 дня.

#### S5.1.D — `telemetry_processing.py` (HL, 1635 строк)

**Файл:** `backend/services/history-logger/telemetry_processing.py`

**Текущее:** функция `process_telemetry_batch()` 1068 строк + класс
`TelemetryQueue`. Смешивает:
- batch decode + validation
- sensor resolution + lazy create
- DB upsert `telemetry_samples` + `telemetry_last`
- realtime broadcast queue → Laravel
- DLQ + retry
- cache (`telemetry_last` in-memory)

**Target structure:**

```
backend/services/history-logger/telemetry/
├── __init__.py
├── batch.py                 # process_telemetry_batch entry point (≤ 300 строк)
├── decode.py                # MQTT payload → typed records
├── sensor_resolver.py       # resolve sensor_id by (zone, node, metric, channel, scope)
├── db_writer.py             # bulk insert telemetry_samples, upsert telemetry_last
├── broadcast.py             # realtime queue + POST /api/internal/realtime/telemetry-batch
├── cache.py                 # in-memory last-value cache (existing)
└── queue.py                 # TelemetryQueue (existing, переезжает сюда)
```

**Acceptance:**
- Существующий `telemetry_processing.py` остаётся как deprecated re-export
  (для legacy импортов).
- `test_history_logger_telemetry_*.py` зелёный без изменений.
- Метрики `telemetry_processed_total{result}` сохраняют label-семантику.

**Риски:** sensor cache invalidation между модулями. Mitigation: cache —
один module-level state в `cache.py`, остальные импортируют функции
доступа.

**Оценка:** 3-4 дня.

#### S5.1.E — `command_status_queue.py` (common, 1652 строки)

**Файл:** `backend/services/common/command_status_queue.py`

**Текущее:** `StatusUpdateQueue` ~790+ строк + global singleton + retry
worker + DLQ + metrics.

**Target structure:**

```
backend/services/common/command_status_queue/
├── __init__.py              # re-export get_status_queue + StatusUpdateQueue
├── queue.py                 # StatusUpdateQueue core (in-memory + DB)
├── retry_worker.py          # background retry с exponential backoff
├── dlq.py                   # DLQ list/replay/purge
└── metrics.py               # Prometheus counters
```

**Acceptance:**
- API через `from common.command_status_queue import get_status_queue` не меняется.
- Все consumers (`history-logger`, `mqtt-bridge`) продолжают работать.
- Существующий `test_command_status_queue.py` зелёный.

**Оценка:** 2 дня.

#### S5.1.F — `ZoneEventMessageFormatter.php` (Laravel, 1497 строк)

**Файл:** `backend/laravel/app/Services/ZoneEventMessageFormatter.php`

**Текущее:** один `format(ZoneEvent $event)` метод с switch на event type,
~80 случаев. Сложно тестировать, сложно добавлять новые event types.

**Target structure (Strategy pattern):**

```
backend/laravel/app/Services/ZoneEventFormatter/
├── ZoneEventMessageFormatter.php       # facade (тонкий, ≤ 100 строк)
├── Contract/
│   └── EventTypeFormatter.php          # interface
└── Formatters/
    ├── CorrectionEventFormatter.php    # EC_DOSING, PH_CORRECTED, CORRECTION_*
    ├── IrrigationEventFormatter.php    # LEVEL_SWITCH_CHANGED, IRRIGATION_*
    ├── SetupEventFormatter.php         # CLEAN_FILL_*, SOLUTION_FILL_*
    ├── AutomationEventFormatter.php    # AE3_*, AUTOMATION_*
    └── DefaultEventFormatter.php       # fallback
```

`ZoneEventMessageFormatter::format()` lookup по `event.type` → выбор
конкретного formatter из реестра.

**Acceptance:**
- Существующие тесты `tests/Unit/Services/ZoneEventMessageFormatterTest.php` зелёные.
- Каждый formatter ≤ 250 строк.
- Новые event types добавляются как новый formatter, не правкой god-метода.

**Оценка:** 2 дня.

#### S5.1.G — `routes/web.php` zone show closure (389 строк)

**Файл:** `backend/laravel/routes/web.php:583-972`

**Текущее:** Inline closure с большой логикой: Inertia props + EffectiveTargets +
devices fetch + 6 кэш-вызовов. Не тестируема как unit.

**Target:**

```
backend/laravel/app/Http/Controllers/ZonePageController.php
└── public function show(Zone $zone): Response  // Inertia::render('Zones/Show', ...)
```

С зависимостями через DI:
- `EffectiveTargetsService`
- `DeviceNodeRepository`
- `ZoneTelemetrySnapshotService`

**Acceptance:**
- `routes/web.php` сокращается на 389 строк.
- Существующие feature тесты на `/zones/{id}` зелёные.
- Новый `tests/Feature/ZonePageControllerTest.php` для покрытия.

**Оценка:** 1 день.

#### S5.1.H — `RecipeEditor.vue` (Frontend, 1708 строк)

**Файл:** `backend/laravel/resources/js/Components/RecipeEditor.vue`

**Target structure:**

```
resources/js/Components/RecipeEditor/
├── RecipeEditorShell.vue          # tabs nav + общий state (≤ 300 строк)
├── PhaseList.vue                  # list of phases с drag-drop
├── phase/
│   ├── PhaseTab.vue               # single phase editor (≤ 400 строк)
│   ├── widgets/
│   │   ├── PhTargetWidget.vue
│   │   ├── EcTargetWidget.vue
│   │   ├── NutrientRatioWidget.vue
│   │   ├── IrrigationWidget.vue
│   │   ├── LightingWidget.vue
│   │   └── DayNightWidget.vue
│   └── usePhaseEditor.ts          # composable со state per phase
└── useRecipeEditor.ts             # composable со root state
```

**Acceptance:**
- Существующие Vitest специи на `RecipeEditor` зелёные (с минимальной правкой моков под новую структуру).
- Каждый компонент ≤ 400 строк.
- Playwright `tests/e2e/browser/specs/06-grow-cycle.spec.ts` зелёный.

**Оценка:** 4-5 дней (большой компонент с reactive state).

#### S5.1.I — `storage_irrigation_node_framework_integration.c` (Firmware, 2774 строки)

**Файл:** `firmware/nodes/storage_irrigation_node/main/storage_irrigation_node_framework_integration.c`

**Target structure:**

```
firmware/nodes/storage_irrigation_node/main/
├── storage_irrigation_node_framework_integration.c   # bootstrap (≤ 400 строк)
├── stages/
│   ├── stage_clean_fill.c          # clean_fill events + handlers
│   ├── stage_solution_fill.c
│   ├── stage_prepare_recirculation.c
│   ├── stage_irrigation.c
│   └── stage_emergency_stop.c
├── commands/
│   ├── handle_set_relay.c          # 252 строки сейчас
│   ├── handle_state.c
│   └── handle_pump_main.c
└── monitoring/
    ├── level_switches.c
    └── pump_health.c
```

**Acceptance:**
- ESP-IDF `idf.py build` зелёный для `storage_irrigation_node`.
- HIL-тесты (`tests/e2e/scenarios/storage_irrigation_*.yaml`) зелёные.
- `firmware/tests/test_storage_*.py` зелёные.

**Риски:** Изменение CMakeLists.txt компонента; статические переменные между
файлами требуют extern declarations. Mitigation: TDD через protocol тесты.

**Оценка:** 5-7 дней.

---

### S5.2 — Унификация publish команд

**Контекст:** В коде существует **три параллельных пути** публикации команд
в MQTT, что нарушает инвариант "history-logger — единственная точка
publish":

1. `history-logger/command_routes.py::POST /commands` → publish (canonical) ✅
2. `mqtt-bridge/publisher.py::Publisher.publish_command()` (legacy direct publish) ❌
3. `automation-engine/.../publish_planned_command.py` (только в тестах, не в boot) ⚠️

Плюс в Laravel — 4 разных HTTP-клиента к AE с разными timeout/retry:
- `Ae3IrrigationBridgeService` (`POST .../start-irrigation`)
- `GrowCycle/GrowCycleAutomationDispatcher` (`POST .../start-cycle`)
- `AutomationScheduler/ScheduleDispatcher` (3 endpoints, `Http::pool`)
- `CommandStatusController` (`GET /internal/tasks/{id}`)

#### S5.2.A — Удалить `mqtt-bridge` direct publish

**Файлы:**
- `backend/services/mqtt-bridge/main.py:296-426` (handlers `send_zone_command`/`send_node_command`)
- `backend/services/mqtt-bridge/publisher.py:96-165` (`Publisher.publish_command`)

**План:**
1. Найти всех consumers `POST /commands/zone/{id}` и `POST /commands/node/{uid}` к mqtt-bridge.
2. Перенаправить на эквивалентные endpoints history-logger (`POST /zones/{id}/commands`, `POST /nodes/{uid}/commands`).
3. Удалить `Publisher.publish_command` и dead handlers в `mqtt-bridge/main.py`.
4. mqtt-bridge остаётся только для:
   - `POST /status-probe` (live MQTT status check)
   - Backward-compat alias endpoints, помеченные deprecated, с redirect на history-logger.

**Acceptance:**
- `make test-mqttb` зелёный (после правки тестов).
- Все Laravel-клиенты (`PythonBridgeService`) уже идут на history-logger (после S1.7 правки) — проверить grep.
- `grep -rn "publish_command" backend/services/mqtt-bridge/` → пусто.

**Риски:** Сломаются интеграции, которые ходят прямо в mqtt-bridge. Mitigation:
оставить proxy endpoints с deprecation log на 1 месяц.

**Оценка:** 2-3 дня.

#### S5.2.B — Подключить или удалить `PublishPlannedCommandUseCase`

**Файлы:**
- `backend/services/automation-engine/ae3lite/application/use_cases/publish_planned_command.py`
- `backend/services/automation-engine/ae3lite/runtime/bootstrap.py:89-94`
- `backend/services/automation-engine/test_ae3lite_publish_planned_command_integration.py`

**Текущее:** Use case существует и покрыт тестами, но **не подключён** в
production boot. Production использует `SequentialCommandGateway._run_command`.

**Решение (выбрать одно):**

**Опция A.** Подключить `PublishPlannedCommandUseCase` в bootstrap и
переключить gateway на него (правильнее по DDD, но рискованнее).

**Опция B.** Удалить `PublishPlannedCommandUseCase` и его тесты как dead
test path (проще, но теряем готовую абстракцию).

**План:** обсудить с тимлидом, выбрать опцию. По дефолту — **Опция B**
(удалить), так как `SequentialCommandGateway` уже purpose-built и решает
тонкости (publish + reconcile в одном loop).

**Оценка:** 1 день.

#### S5.2.C — Унифицировать Laravel → AE3 HTTP-клиенты

**Файлы:**
- `app/Services/Ae3IrrigationBridgeService.php`
- `app/Services/GrowCycle/GrowCycleAutomationDispatcher.php`
- `app/Services/AutomationScheduler/ScheduleDispatcher.php`
- `app/Http/Controllers/CommandStatusController.php`

**Target:**

```
app/Services/Ae3/
├── Ae3Client.php              # единая обёртка над Http::pool() с таймаутами,
│                              # auth headers, X-Trace-Id, X-Scheduler-Id,
│                              # retry policy
├── Endpoints/
│   ├── StartCycle.php
│   ├── StartIrrigation.php
│   ├── StartLightingTick.php
│   ├── GetInternalTask.php
│   └── ZoneControlMode.php
└── Ae3Exception.php
```

**Acceptance:**
- Existing services делегируют на `Ae3Client`.
- Все endpoints в одном месте, одна точка тестирования.
- Feature тесты `ScheduleDispatcherTest`, `Ae3IrrigationBridgeServiceTest`,
  `GrowCycleAutomationDispatcherTest` зелёные.

**Оценка:** 2-3 дня.

---

### S5.3 — Регистрация Policy + переход на `$user->can(...)`

**Файлы:**
- `backend/laravel/app/Providers/AuthServiceProvider.php:18-21`
- `backend/laravel/app/Policies/ZonePolicy.php` (есть)
- `backend/laravel/app/Policies/DeviceNodePolicy.php` (есть)
- `backend/laravel/app/Policies/CommandPolicy.php` (есть)
- `backend/laravel/app/Helpers/ZoneAccessHelper.php`

**Проблема:** Policy классы существуют, но **не зарегистрированы** в
`AuthServiceProvider::$policies` (зарегистрированы только `GrowCyclePolicy`,
`RecipeRevisionPolicy`). Защита mutating endpoints — через
`ZoneAccessHelper::canAccessZone()` + `role:` middleware, не через Laravel
Policy. Это:
- усложняет авторизационный аудит (нельзя `php artisan policies`);
- мешает использовать `@can` в blade/Inertia;
- ломает паттерн `$this->authorize(...)` в контроллерах.

**План:**

1. Зарегистрировать в `AuthServiceProvider::$policies`:
   ```php
   protected $policies = [
       GrowCycle::class => GrowCyclePolicy::class,
       RecipeRevision::class => RecipeRevisionPolicy::class,
       Zone::class => ZonePolicy::class,                  // NEW
       DeviceNode::class => DeviceNodePolicy::class,      // NEW
       Command::class => CommandPolicy::class,            // NEW
   ];
   ```

2. Сверить методы Policy с фактической логикой `ZoneAccessHelper`.
   Если есть delta — синхронизировать.

3. В контроллерах постепенно заменить:
   ```php
   if (! ZoneAccessHelper::canAccessZone($user, $zone)) abort(403);
   ```
   на:
   ```php
   $this->authorize('view', $zone);
   ```

4. `ZoneAccessHelper` остаётся как helper, который **внутри** вызывает
   `Policy` (DRY — Policy остаётся source of truth).

**Acceptance:**
- `php artisan route:list --columns=method,uri,middleware` показывает
  Policy-based access для всех zone/device/command routes.
- Существующие тесты на authorization зелёные.
- Новый `tests/Unit/Policies/ZonePolicyTest.php` с покрытием 5 ролей × 4 actions.
- `grep -rn "ZoneAccessHelper::canAccessZone" backend/laravel/app/Http/Controllers/` —
  только legacy contexts, основные mutating routes — на `$this->authorize`.

**Риски:** Policy и `ZoneAccessHelper` могут давать разные ответы для
edge-cases (например, viewer + greenhouse через user_greenhouses). Mitigation:
сначала characterization tests на текущее `ZoneAccessHelper`, потом
синхронизировать `ZonePolicy`.

**Оценка:** 2-3 дня.

---

### S5.4 — Decouple domain ↔ infra leakage в AE3

**Файлы (текущие boundary violations):**

1. `domain/services/cycle_start_planner.py:9-10` — импорт из `application/dto/*`
2. `domain/services/cycle_start_planner.py:15` — импорт Prometheus метрик
3. `domain/services/correction_transition_policy.py:28` — импорт `StageOutcome` из application
4. `application/handlers/base.py:29-30,132` — прямой `common.db.get_pool`
5. `application/use_cases/create_task_from_intent.py:11,71-77` — прямой `common.db.get_pool` + advisory lock SQL

**Принцип (DDD/Clean Architecture):**

```
domain/          ← чистые value objects, entities, domain services
                   НЕТ импорта из application/, infrastructure/, common/
application/     ← use cases, handlers
                   импортирует domain/, НЕ импортирует infrastructure/
infrastructure/  ← репозитории, gateways, clients, метрики
                   реализует interfaces из application/
runtime/         ← bootstrap, app, DI wiring
```

**План:**

#### S5.4.A — Вынести метрики из `domain/services/`

**До:**
```python
# domain/services/cycle_start_planner.py
from ae3lite.infrastructure.metrics import CYCLE_START_DECISIONS_TOTAL
CYCLE_START_DECISIONS_TOTAL.labels(...).inc()
```

**После:**
```python
# domain/services/cycle_start_planner.py
# никаких import metrics

class CycleStartPlanner:
    def plan(self, ...) -> CycleStartDecision:
        decision = ...
        return decision  # decision содержит достаточно данных для метрик
```

```python
# application/use_cases/create_task_from_intent.py (consumer)
decision = planner.plan(...)
CYCLE_START_DECISIONS_TOTAL.labels(outcome=decision.outcome).inc()
```

**Acceptance:**
- `grep -rn "from.*infrastructure.metrics" ae3lite/domain/` → пусто.
- Метрики продолжают пишутся (теперь в application layer).
- Существующие тесты AE3 зелёные.

**Оценка:** 1-2 дня.

#### S5.4.B — Application: убрать прямой SQL/pool acquire

**Текущее:** `application/handlers/base.py::_checkpoint()` напрямую вызывает
`get_pool()` и пишет SQL для чтения `zones.config_mode/config_revision`.

**Target:** ввести репозиторий-интерфейс на уровне application:

```python
# application/ports/zone_config_repository.py (NEW)
class ZoneConfigRepository(Protocol):
    async def read_config_state(self, zone_id: int) -> ZoneConfigState: ...
```

```python
# infrastructure/repositories/zone_config_repository.py (NEW)
class PgZoneConfigRepository(ZoneConfigRepository):
    async def read_config_state(self, zone_id: int) -> ZoneConfigState:
        async with (await get_pool()).acquire() as conn:
            row = await conn.fetchrow(...)
            return ZoneConfigState(...)
```

Handler получает `ZoneConfigRepository` через ctor injection из bootstrap.

**Acceptance:**
- `grep -rn "from common.db import" ae3lite/application/` → пусто.
- `grep -rn "get_pool()" ae3lite/application/` → пусто (только в `infrastructure/`).
- Все existing AE3 тесты зелёные.

**Риски:** Большая поверхность изменений (десятки call-sites). Mitigation:
поэтапно — сначала вынести `_checkpoint`, затем `create_task_from_intent`,
и т.д. Каждый шаг — отдельный коммит.

**Оценка:** 4-5 дней.

---

### S5.5 — Frontend composables boundary + типы

**Файлы:**

1. `resources/js/composables/useZones.ts` (158 строк) — list + cache + reload
2. `resources/js/composables/useZonePageState.ts` (624 строк) — Inertia + Pinia + WS + telemetry
3. `resources/js/composables/useZoneShowPage.ts` (450 строк) — orchestrator Show.vue
4. Дубликаты типов между `schemas/`, `types/`, `services/api/`

**Проблема:** Перекрывающиеся ответственности; неясно где SSOT для zone state.

**План:**

#### S5.5.A — Чёткая roles-decomposition композаблов зоны

**Target:**

| Composable | Ответственность | Не делает |
|------------|-----------------|-----------|
| `useZones()` | список зон (cache + reload через Inertia) | не управляет single zone state |
| `useZonePageState()` | **SSOT** для single zone state (zone, cycle, telemetry, events, alerts), WS-подписки | не управляет UI (tabs, modals) |
| `useZoneShowPage()` | UI orchestration для `Pages/Zones/Show.vue` (tabs, modals, chart, scroll position) | не подписывается на WS напрямую, использует exposed event emitter из `useZonePageState` |
| `useZoneAutomationScheduler()` | AE3 runtime state + manual steps | не подписывается на WS напрямую, использует event emitter из `useZonePageState` |

**Зависимости:**
- `useZoneShowPage` и `useZoneAutomationScheduler` получают reactive zone state и event-stream через explicit composable composition, не через прямые WS-подписки.

**Acceptance:**
- Vitest: новый `useZonePageState.events.spec.ts` тестирует event emitter API.
- Vitest: refactored `useZoneShowPage` не имеет прямых `subscribeManagedChannelEvents` вызовов.
- Vitest: refactored `useZoneAutomationScheduler` — то же.
- Manual test: при открытой Automation вкладке `.EventCreated` приводит к **одному** reload zone (не двум), proven via mock counter.

**Оценка:** 3-4 дня.

#### S5.5.B — Унификация типов

**Проблема:** `interface ZoneApiEvent` в 3 компонентах независимо; `interface Zone` в `ZoneCreateWizard.vue:101` локальный вместо `@/types/Zone`.

**План:**

1. Аудит `grep -rn "interface Zone\b\|interface ZoneApiEvent" resources/js/` → собрать все локальные определения.
2. Канонические типы — в `resources/js/types/Zone.ts` и `resources/js/types/Event.ts`.
3. Заменить локальные определения на импорт canonical.
4. Lint rule (`@typescript-eslint/no-redeclare` + custom) — запретить дубликаты.

**Acceptance:**
- `grep -rn "interface Zone " resources/js/` → только в `types/`.
- TypeScript typecheck зелёный.
- Vitest зелёный.

**Оценка:** 1 день.

---

### S5 — Definition of Done (общий)

- [ ] Каждый sub-task — отдельный PR с green CI.
- [ ] Каждый PR содержит `Compatible-With:` строку.
- [ ] К каждому рефакторингу добавлен characterization-тест **до** изменений
      (чтобы зафиксировать текущее observable behavior).
- [ ] Документация обновлена синхронно (`doc_ai/04_BACKEND_CORE/ae3lite.md`,
      `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`, и т.д.).
- [ ] Размер файлов в repo (`wc -l`) для god-классов сокращён минимум на 60%.
- [ ] Все слои продолжают проходить полный test suite после каждого PR.
- [ ] `Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.

### S5 — Общая оценка

| Sub-task | Дней (1 разработчик) |
|----------|---------------------:|
| S5.1.A correction.py | 3-5 |
| S5.1.B base.py | 2-3 |
| S5.1.C execute_task.py | 2-3 |
| S5.1.D telemetry_processing.py | 3-4 |
| S5.1.E command_status_queue.py | 2 |
| S5.1.F ZoneEventMessageFormatter.php | 2 |
| S5.1.G zone show closure | 1 |
| S5.1.H RecipeEditor.vue | 4-5 |
| S5.1.I storage_irrigation_node | 5-7 |
| S5.2.A удалить mqtt-bridge publish | 2-3 |
| S5.2.B publish_planned_command | 1 |
| S5.2.C Ae3Client | 2-3 |
| S5.3 Policies | 2-3 |
| S5.4.A метрики из domain | 1-2 |
| S5.4.B Application repo interfaces | 4-5 |
| S5.5.A composables roles | 3-4 |
| S5.5.B типы | 1 |
| **ИТОГО** | **40-56 дней** (8-11 weeks для одного разработчика) |

С параллелизацией двух-трёх агентов — 4-6 недель.

---

## Track вне приоритетов (для backlog)

- **B1.** Magic numbers → config (AE3 `_IRR_PROBE_FAILURE_STREAK_LIMIT` etc.)
- **B2.** Naming `'gh-1'` fallback → fail-closed на отсутствие greenhouse uid
- **B3.** `Cache::remember(zones_list_*)` invalidation на mutations
- **B4.** `:latest` → pinned tags в всех Docker compose
- **B5.** Plain-text passwords → Docker secrets / env file
- **B6.** Prometheus scrape добавить digital-twin/aggregator/feature-builder
- **B7.** Alert rules — добавить `runbook` / `owner` labels
- **B8.** Replace `xSemaphoreTake(..., portMAX_DELAY)` на bounded timeout в trema_ec/trema_ph
- **B9.** Watchdog `node_watchdog_add_task` на storage_irrigation_node `cmd_queue_task`
- **B10.** Migrate `corr_*_amount_ml` `float` → `numeric(12,3)` (если есть данные — backfill)
- **B11.** Завершить S2.4 (HL handlers → http_client_pool): обновить 8 тестов
  в `test_critical_fixes.py::TestLaravelApiRetry` и
  `test_format_sync_integration.py` — заменить mocking `httpx.AsyncClient`
  context manager на `get_http_client()`. На текущем этапе попытка перевода
  сломала 8 production тестов; откат сделан в Stage 2 коммите.

---

## Что НЕ входит

- Полная переархитектура (slow refactoring без бизнес-обоснования)
- Удаление dead code (отдельный low-priority cleanup)
- Стилистические правки (pint/eslint уже выполнены)
- Обновление зависимостей (отдельный security audit)

---

## Ссылки

- Полный аудит: внутренний chat-транскрипт от 2026-05-28
- doc_ai sync: коммит `b7b72344 docs(sync): align doc_ai with actual runtime code across 4 layers`
- IP whitelist + sensors index: коммит `59229bd5 fix(security,db): enforce node IP whitelist + restore sensors canonical UNIQUE`
