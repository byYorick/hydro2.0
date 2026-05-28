# AUDIT_2026_05_28_BUGFIX_PLAN.md
# План багфиксов по результатам code-аудита 2026-05-28

**Дата:** 2026-05-28
**Версия:** 1.0
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

## Карта приоритетов

| Этап | Тема | Объём | Срочность | Риск регрессии |
|------|------|-------|-----------|----------------|
| **S1** | Security fast-track | ~12 файлов | **CRITICAL** | низкий (аддитивно) |
| **S2** | Code-bug фиксы | ~6 файлов | **HIGH** | средний |
| **S3** | Timescale compression policies | 1 миграция | **HIGH** | низкий |
| **S4** | WS dedup на frontend | 4 файла | **HIGH** | средний |
| **S5** | Архитектурный рефакторинг | большой | medium | высокий |

---

## Этап S1 — Security fast-track

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

## Этап S2 — Code-bug фиксы

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

## Этап S3 — Timescale compression policies

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

## Этап S4 — WS dedup на frontend

### S4.1 — Унификация подписок на `hydro.zones.{id}`

**Файлы:**
- `backend/laravel/resources/js/composables/useZonePageState.ts:495–545`
- `backend/laravel/resources/js/composables/useZoneShowPage.ts:180–186`
- `backend/laravel/resources/js/composables/useZoneAutomationScheduler.ts:184–213`

**Проблема:** 6 параллельных листенеров на одну зону при активной вкладке Automation.

**План:**
- Single source of truth для zone-channel — `useZonePageState`.
- `useZoneShowPage` и `useZoneAutomationScheduler` подписываются на shared event emitter из `useZonePageState`, не на raw channel.
- Удалить дублирующие handler на `.EventCreated` + `.App\Events\EventCreated` (через alias resolver в `useZonePageState`).
- Гарантировать `unsubscribeAll()` при unmount Show.

**Acceptance:**
- Vitest: новый тест `useZoneShowPage.websocket.spec.ts` проверяет один listener.
- Manual test: открыть Show с вкладкой Automation, прислать EventCreated → `reload` вызывается **один раз** (assert через mock).

---

## Этап S5 — Архитектурный рефакторинг (track, не одна задача)

### S5.1 — God-классы → разбиение

Кандидаты на splitting:

| Файл | Текущий размер | Целевые модули |
|------|---------------:|----------------|
| `ae3lite/application/handlers/correction.py` (2307) | god | check / dose_ec / dose_ph / observe / no_effect / limits |
| `ae3lite/application/handlers/base.py` (2004) | god | checkpoint / probe / sensor_bounds / level_monitor proxy |
| `ae3lite/application/use_cases/execute_task.py` (1387) | god | execute / snapshot_load / topology_verify |
| `history-logger/telemetry_processing.py` (1635) | god | ingress / cache / db_writer / broadcast / dlq |
| `common/command_status_queue.py` (1652) | god | queue / retry_worker / dlq / metrics |
| `app/Services/ZoneEventMessageFormatter.php` (1497) | god | per-event-type formatter classes |
| `routes/web.php` zone show closure (389) | inline | `ZonePageController@show` |
| `resources/js/Components/RecipeEditor.vue` (1708) | god | RecipeEditorShell + phase tabs + per-phase widgets |
| `firmware/nodes/storage_irrigation_node/main/storage_irrigation_node_framework_integration.c` (2774) | god | разнести по `stage_*.c` модулям |

### S5.2 — Унификация publish команд

- Удалить `Publisher.publish_command` из `mqtt-bridge` (legacy)
- Подключить `PublishPlannedCommandUseCase` в AE3 production boot (или удалить из репозитория как dead test path)
- Унифицировать 4 Laravel HTTP-клиента к AE через single `Ae3Client` service

### S5.3 — Регистрация Policy

- Зарегистрировать `ZonePolicy`, `DeviceNodePolicy`, `CommandPolicy` в `AuthServiceProvider`
- Заменить `ZoneAccessHelper::canAccessZone()` checks на `$user->can('view', $zone)` в контроллерах

### S5.4 — Decouple domain → infra leakage в AE3

- `domain/services/cycle_start_planner.py` — убрать импорт из `application/*` и infra metrics
- `domain/services/correction_transition_policy.py` — то же

### S5.5 — Frontend: composables boundary

- Определить single source of truth для zone state: `useZonePageState` (canonical), `useZoneShowPage` (orchestrator), `useZoneAutomationScheduler` (subscriber)
- Удалить дубликаты типов между `schemas/`, `types/`, `services/api/`

### S5 — Definition of Done

- Каждый sub-task — отдельный PR с тестами
- Не блокирует S1–S4
- Время реализации: недели

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
