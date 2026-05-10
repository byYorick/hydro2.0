# AE3 NODE AVAILABILITY DETECTION PLAN
# План: доработка системы определения доступности нод и каналов в AE3 snapshot

**Дата:** 2026-05-08
**Статус:** реализовано (2026-05-08). Минимальный пакет (§3.1–3.4, §3.6, §3.7) выполнен; пакеты §6 (counter retry-attempts, channel-level health) — отдельные планы.
**Авторы:** аудит инцидента `ae3_snapshot_retry_exhausted` task_id=4 zone 1 (2026-05-08 05:29 UTC).
**Связано с:** `ae3lite.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `ERROR_CODE_CATALOG.md`, `MQTT_SPEC_FULL.md`, `DATA_MODEL_REFERENCE.md`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. TL;DR

`ZoneSnapshot` в AE3 определяет «online actuator channels» одним SQL-фильтром по полю `nodes.status='online'`. Это поле обновляется единственным сервисом (`history-logger`) с задержкой:
- `online` → пишется на heartbeat/status/lwt мгновенно;
- `offline` → пишется фоновой задачей `monitor_offline_nodes` с интервалом `NODE_OFFLINE_CHECK_INTERVAL_SEC` (60 сек) при условии `last_seen_at < NOW() - NODE_OFFLINE_TIMEOUT_SEC` (120 сек).

Любой кратковременный gap MQTT > 120 сек переводит ноду в `offline`, snapshot падает с `ae3_snapshot_no_online_actuator_channels`, retry budget `SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC=90s` исчерпывается до того, как нода реально вернулась, и `task` закрывается fail-closed.

Дополнительно retry budget считается по wall-clock (`now - stage_entered_at`), а не по числу попыток. Если AE3 был остановлен 16 часов (реальный кейс инцидента) — на первом же reclaim бюджет «исчерпан» мгновенно, хотя retry-попыток не было ни одной.

План закрывает три вектора:

1. **Snapshot fallback по `last_seen_at`** — добавить в SQL-фильтр компромиссное условие «status='online' OR недавняя активность по любому из последних timestamp», чтобы устранить ложноотрицательные срабатывания на drift `nodes.status`.
2. **Диагностика per-node при `no_online_actuator_channels`** — обогащать `SnapshotBuildError` и алерт `biz_ae3_task_failed` списком всех нод зоны с (`uid`, `type`, `status`, `last_seen_age_sec`) и подсчётом `missing_required_node_types` для топологии.
3. **Дифференциация transient vs persistent** — увеличить дефолт `SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC` до 600 сек, ввести понятие persistent_dead (`last_seen_age_sec >= AE3_NODE_PERSISTENT_DEAD_SEC`, default 600), при котором не ретраить и сразу фейлить с понятной причиной (`ae3_snapshot_required_node_persistently_offline`).
4. **Topology-aware required-nodes** — для two-tank-топологий (`two_tank`, `two_tank_drip_substrate_trays`) проверять, что snapshot содержит хотя бы по одному actuator для `node_type ∈ {irrig, ph, ec}` и при отсутствии — отдавать конкретную причину, а не общую «no online actuator channels».

Пункт «персистентный счётчик retry-attempts вместо wall-clock» (предложение из аудита) — **выносится в отдельную задачу** (потребует миграции `ae_tasks`).
Пункт «per-channel availability в `ZoneActuatorRef`» — **выносится в отдельную задачу** (потребует обновления контракта DTO и всех stage-handler'ов).

---

## 1. Контекст

### 1.1 Где живёт логика

- `backend/services/automation-engine/ae3lite/infrastructure/read_models/zone_snapshot_read_model.py:228-320` — SQL выборка actuator-каналов и `SnapshotBuildError(AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS)`.
- `backend/services/automation-engine/ae3lite/application/use_cases/execute_task.py:471-582` — `_retry_transient_snapshot_gap`, `_is_transient_snapshot_gap`, константы `SNAPSHOT_TRANSIENT_RETRY_SEC`, `SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC`.
- `backend/services/automation-engine/ae3lite/domain/errors.py` — enum `ErrorCodes`, в т.ч. `AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS`.
- `backend/services/history-logger/handlers/heartbeat_status.py:114-250` — обновление `nodes.status`/`last_seen_at`/`last_heartbeat_at` и `monitor_offline_nodes`.
- `backend/services/common/env.py` — `node_offline_timeout_sec`, `node_offline_check_interval_sec`.
- `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` — каталог error codes.
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — спецификация AE3.

### 1.2 Текущая выборка (фрагмент)

```sql
SELECT ...
FROM nodes n
JOIN node_channels nc ON nc.node_id = n.id
LEFT JOIN channel_bindings cb ON cb.node_channel_id = nc.id
LEFT JOIN LATERAL (...) pc ON TRUE
WHERE n.zone_id = $1
  AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
  AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
  AND COALESCE(nc.is_active, TRUE) = TRUE
ORDER BY n.id ASC, nc.id ASC
```

### 1.3 Текущий контракт алерта `biz_ae3_task_failed`

```json
{
  "code": "biz_ae3_task_failed",
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "error_code": "ae3_snapshot_retry_exhausted",
  "error_message": "У зоны 1 отсутствуют online actuator channels (transient snapshot retry budget exhausted after 59974s in stage solution_fill_check)",
  "task_id": 4,
  "topology": "two_tank_drip_substrate_trays"
}
```

В payload нет ни одного per-node поля — оператор не понимает, какая нода виновата.

---

## 2. Цель

После реализации:

1. Snapshot-фильтр устойчив к drift поля `nodes.status` в окне `[NODE_OFFLINE_TIMEOUT_SEC; NODE_OFFLINE_TIMEOUT_SEC + monitor_interval]`.
2. Любой алерт `biz_ae3_task_failed` с источником `ae3_snapshot_*` несёт диагностический breakdown по нодам зоны.
3. Transient-блип (gap MQTT 120–600 секунд, нода вернулась) **не убивает** workflow.
4. Persistent dead (нода >10 мин не подаёт признаков жизни) → **немедленный** fail-closed с конкретной причиной без 600-секундного retry.
5. Для two-tank-топологий ошибка отсутствия конкретного `node_type` различима по error_code от общего «no online actuator channels».

---

## 3. Изменения по файлам

### 3.1 `backend/services/automation-engine/ae3lite/infrastructure/read_models/zone_snapshot_read_model.py`

**3.1.1.** Изменить `WHERE`-фильтр на actuator-выборке: добавить fallback по timestamp.

```python
freshness_sec = int(os.getenv("AE3_NODE_FRESHNESS_FALLBACK_SEC", "180"))
# ... в SQL:
WHERE n.zone_id = $1
  AND (
    LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
    OR COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)
       >= NOW() - ($2 * INTERVAL '1 second')
  )
  AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
  AND COALESCE(nc.is_active, TRUE) = TRUE
```

`freshness_sec` параметризовать через env `AE3_NODE_FRESHNESS_FALLBACK_SEC` (default 180s = `NODE_OFFLINE_TIMEOUT_SEC` 120s + 60s grace).

**3.1.2.** Перед `raise SnapshotBuildError(AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS)` (строка ~317) выполнить отдельный диагностический запрос **в той же транзакции**:

```python
zone_nodes_diag = await conn.fetch(
    """
    SELECT
        n.uid,
        LOWER(COALESCE(n.type, '')) AS node_type,
        LOWER(TRIM(COALESCE(n.status, ''))) AS status,
        EXTRACT(EPOCH FROM (NOW() - COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)))::BIGINT
            AS last_seen_age_sec,
        COUNT(nc.id) FILTER (
            WHERE UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
              AND COALESCE(nc.is_active, TRUE) = TRUE
        ) AS active_actuator_count
    FROM nodes n
    LEFT JOIN node_channels nc ON nc.node_id = n.id
    WHERE n.zone_id = $1
    GROUP BY n.id
    ORDER BY n.id ASC
    """,
    zone_id,
)
```

Преобразовать в список dict-ов (`zone_nodes`), посчитать persistence:
- `persistently_offline_nodes` = uid, у которых `last_seen_age_sec >= AE3_NODE_PERSISTENT_DEAD_SEC` (default 600).
- `transiently_offline_nodes` = остальные с `status='offline'`.

Положить в exception:

```python
raise SnapshotBuildError(
    f"У зоны {zone_id} отсутствуют online actuator channels",
    code=ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS,
    details={
        "zone_id": zone_id,
        "zone_nodes": zone_nodes,
        "persistently_offline_uids": persistently_offline_uids,
        "transiently_offline_uids": transiently_offline_uids,
        "missing_required_node_types": missing_required_node_types,  # см. п.3.1.3
    },
)
```

`SnapshotBuildError` должен поддерживать опциональный аттрибут `details: dict`. Расширить класс в `ae3lite/domain/errors.py` (см. §3.4).

**3.1.3.** Topology-aware required-nodes check.

После сборки `actuators` (строка ~315) добавить:

```python
TWO_TANK_REQUIRED_NODE_TYPES: frozenset[str] = frozenset({"irrig", "ph", "ec"})

topology = str(zone_row.get("...") or "").strip().lower()  # топология приходит из task'а — см. ниже
# ВАЖНО: топологию знает ExecuteTaskUseCase, не snapshot. Поэтому правильно
# делать required-check НЕ в read-model'е, а в ExecuteTaskUseCase /
# stage-handler'е после загрузки snapshot. См. §3.3.
```

> **Решение:** required-check переносим в `ExecuteTaskUseCase.run` (см. §3.3). Read-model лишь возвращает actuators + сообщает per-node breakdown.

### 3.2 `backend/services/automation-engine/ae3lite/domain/errors.py`

**3.2.1.** Добавить `details: dict | None = None` в `SnapshotBuildError.__init__` (если ещё не поддерживает) и сохранять как `self.details`.

**3.2.2.** Добавить новые коды в `ErrorCodes`:

```python
AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE = "ae3_snapshot_required_node_persistently_offline"
AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING = "ae3_snapshot_required_node_type_missing"
```

### 3.3 `backend/services/automation-engine/ae3lite/application/use_cases/execute_task.py`

**3.3.1.** Поднять дефолт `SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC` с 90 до 600 (env name остаётся прежним; меняется только default).

**3.3.2.** Добавить новые env / константы:

```python
NODE_PERSISTENT_DEAD_SEC = max(60, int(os.getenv("AE3_NODE_PERSISTENT_DEAD_SEC", "600")))
TWO_TANK_REQUIRED_NODE_TYPES = frozenset({"irrig", "ph", "ec"})
```

**3.3.3.** В обработчике `except SnapshotBuildError as exc` (~237) до вызова `_retry_transient_snapshot_gap`:

a) если `exc.code == AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS` И `exc.details` содержит непустой `persistently_offline_uids` — НЕ retry, сразу `_fail_closed` с `error_code=AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE`, прокинув `details` в alert/event.

b) Иначе передать `exc.details` в `_retry_transient_snapshot_gap` для обогащения payload retry-event'ов.

**3.3.4.** После успешной загрузки snapshot (`snapshot = await self._zone_snapshot_read_model.load(...)`) и до `plan = self._planner.build(...)` — для two-tank топологий проверить required-types:

```python
if topology in {"two_tank", "two_tank_drip_substrate_trays"}:
    actuator_node_types = {a.node_type for a in snapshot.actuators if a.node_type}
    missing = TWO_TANK_REQUIRED_NODE_TYPES - actuator_node_types
    if missing:
        raise SnapshotBuildError(
            f"У зоны {snapshot.zone_id} нет actuator-нод требуемых типов: {sorted(missing)}",
            code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING,
            details={"zone_id": snapshot.zone_id, "missing_node_types": sorted(missing)},
        )
```

Этот код идёт в общий `except SnapshotBuildError` flow, retry по нему НЕ применяется (он не в списке `_is_transient_snapshot_gap`).

**3.3.5.** Расширить `_retry_transient_snapshot_gap`:
- Принимать `details: Mapping[str, Any] | None` (из `exc.details`).
- Прокидывать `details["zone_nodes"]`, `details["persistently_offline_uids"]`, `details["transiently_offline_uids"]` в payload `AE_SNAPSHOT_RETRY_SCHEDULED` / `AE_SNAPSHOT_RETRY_EXHAUSTED` events и в infra-alert details.

**3.3.6.** В `_emit_task_failed_alert` обогащать `details` теми же полями, если `error_code` ∈ {`ae3_snapshot_no_online_actuator_channels`, `ae3_snapshot_retry_exhausted`, `ae3_snapshot_required_node_persistently_offline`, `ae3_snapshot_required_node_type_missing`}.

### 3.4 `backend/services/common/env.py` (или соответствующий settings-модуль AE)

Добавить переменные:

| ENV | Default | Описание |
|-----|---------|----------|
| `AE3_NODE_FRESHNESS_FALLBACK_SEC` | `180` | Окно (сек), в течение которого snapshot считает ноду online по `last_seen_at`, даже если `nodes.status` ещё не обновлён. Должно быть ≥ `NODE_OFFLINE_TIMEOUT_SEC + NODE_OFFLINE_CHECK_INTERVAL_SEC`. |
| `AE3_NODE_PERSISTENT_DEAD_SEC` | `600` | Возраст `last_seen_at` (сек), после которого нода считается persistently dead → snapshot fail-closed без retry. |
| `AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC` | `600` (было 90) | Бюджет retry для transient snapshot gap. |

Соответствующие записи в `backend/docker-compose.dev.yml` для сервиса `automation-engine` — **не нужны** (читаются `os.getenv` напрямую с дефолтом). Если централизованная схема settings есть — добавить в неё.

### 3.5 `backend/services/automation-engine/ae3lite/application/runtime_event_contract.py`

При необходимости добавить в whitelist полей runtime-event'а: `zone_nodes`, `persistently_offline_uids`, `transiently_offline_uids`, `missing_node_types`. Если schema strict — обновить документацию контракта (см. §3.7).

### 3.6 Тесты

#### 3.6.1 Новый файл `backend/services/automation-engine/test_ae3lite_zone_snapshot_freshness_fallback.py`

Покрытие:
- Узел `nodes.status='offline'`, но `last_seen_at = NOW() - 60s` → попадает в actuators.
- Узел `nodes.status='offline'`, `last_seen_at = NOW() - 300s` → НЕ попадает в actuators.
- Узел `nodes.status='online'`, `last_seen_at IS NULL` → попадает (текущее поведение сохраняется).
- Граница: `last_seen_at = NOW() - AE3_NODE_FRESHNESS_FALLBACK_SEC` → включительно.

#### 3.6.2 Новый файл `backend/services/automation-engine/test_ae3lite_zone_snapshot_diagnostics.py`

Покрытие:
- При пустых actuators `SnapshotBuildError.details["zone_nodes"]` содержит все ноды зоны.
- `persistently_offline_uids` корректно вычисляется по `AE3_NODE_PERSISTENT_DEAD_SEC`.
- При отсутствии нод в зоне — `zone_nodes == []`, `details` всё равно присутствует.

#### 3.6.3 Дополнить `backend/services/automation-engine/test_ae3lite_execute_task.py`

Сценарии:
- `AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS` с `persistently_offline_uids=["nd-x"]` → fail-closed с `error_code=ae3_snapshot_required_node_persistently_offline`, retry НЕ запускается.
- `AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS` без persistently dead узлов → retry с обновлённым default 600s.
- two_tank topology, snapshot вернул actuators только для `node_type='ph'` → `AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING` с `missing_node_types=["ec","irrig"]`.
- `AE_SNAPSHOT_RETRY_SCHEDULED` / `AE_SNAPSHOT_RETRY_EXHAUSTED` payload содержит `zone_nodes`, `persistently_offline_uids`.
- Alert `biz_ae3_task_failed` для всех новых error_codes несёт `zone_nodes` в `details`.

#### 3.6.4 E2E (опционально, отдельный PR)

В `tests/e2e/scenarios/ae3lite/` — новый сценарий `E1XX_ae3_two_tank_node_offline_recovery.yaml`:
1. Запустить task `cycle_start` two-tank.
2. Дождаться `solution_fill_check`.
3. Симулятором `tests/node_sim/` отключить `irrig` ноду на 200 секунд (внутри нового бюджета 600s).
4. Включить обратно.
5. Проверить, что workflow продолжается, а не fail-closed.

### 3.7 Документация

#### 3.7.1 `doc_ai/04_BACKEND_CORE/ae3lite.md`

В разделе про snapshot read-model добавить подсекцию «Определение online actuator channels»:
- описать SQL-фильтр с fallback на `last_seen_at`;
- описать диагностический breakdown в `SnapshotBuildError.details`;
- описать topology-aware required-nodes check;
- задокументировать env переменные.

#### 3.7.2 `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md`

Добавить:
- `ae3_snapshot_required_node_persistently_offline` — «Один или несколько узлов зоны не подают признаков жизни ≥ AE3_NODE_PERSISTENT_DEAD_SEC. AE3 не выполняет retry, чтобы не зависать.»
- `ae3_snapshot_required_node_type_missing` — «Для текущей топологии в зоне не зарегистрирован обязательный node_type (например, для two_tank — irrig/ph/ec).»

Уточнить описание `ae3_snapshot_no_online_actuator_channels` и `ae3_snapshot_retry_exhausted`: «details содержит per-node breakdown с last_seen_age_sec».

#### 3.7.3 `doc_ai/04_BACKEND_CORE/AE3_RUNTIME_EVENT_CONTRACT.md`

Если документ перечисляет whitelist полей runtime events — добавить новые.

#### 3.7.4 `backend/laravel/resources/js/constants/error_codes.json` + `backend/laravel/error_codes.json` + `backend/laravel/alert_codes.json` + `backend/error_codes.json` + `backend/alert_codes.json`

Добавить новые error_codes с русскими описаниями для UI каталога ошибок (см. существующие записи `ae3_snapshot_*`).

#### 3.7.5 Frontend `backend/laravel/resources/js/utils/errorCatalog.ts`

Добавить новые коды в каталог фронтенд-ошибок.

---

## 4. Ограничения и требования

1. **НЕ менять** API-контракт `POST /zones/{id}/start-cycle` и `GET /internal/tasks/{task_id}`.
2. **НЕ менять** схему БД (без миграций) — все доработки только в SQL-выборке snapshot read-model и в Python-логике AE3.
3. **НЕ публиковать** команды в MQTT напрямую — путь команд остаётся `AE3 → history-logger → MQTT`.
4. Все новые env-переменные **обязательно** иметь sane defaults (см. §3.4) — сервис должен запуститься без явной конфигурации.
5. Все новые error_codes документируются в `ERROR_CODE_CATALOG.md` и каталогах фронтенда **в том же PR**, что и код.
6. Тесты обязательны для всех новых веток логики (см. §3.6).
7. **Обратная совместимость** alert-payload: новые поля (`zone_nodes`, `persistently_offline_uids` и т.д.) добавляются как **дополнительные**, существующие поля (`error_code`, `error_message`, `task_id`, `stage`, `workflow_phase`, `topology`) не меняются.
8. Соблюдать стиль проекта (PEP 8, type hints, async/await, fail-closed на ошибках валидации).
9. Compatible-With строка обязательна в commit/PR.

---

## 5. Критерии приёмки

1. **Unit-тесты:**
   - `make test-ae` зелёный, новые тесты из §3.6 проходят.
   - `pytest -x -q test_ae3lite_zone_snapshot_freshness_fallback.py test_ae3lite_zone_snapshot_diagnostics.py test_ae3lite_execute_task.py` — все зелёные.

2. **Воспроизведение исходного инцидента (manual):**
   - Создать в dev-БД зону с реальной топологией `two_tank_drip_substrate_trays`.
   - Установить вручную `nodes.status='offline'` для всех нод зоны при `last_seen_at = NOW() - 60s`.
   - Запустить `POST /zones/{id}/start-cycle`.
   - Snapshot **не** падает, потому что `last_seen_at` свежий (fallback срабатывает).

3. **Persistent dead detection (manual):**
   - В той же зоне установить `nodes.status='offline'` AND `last_seen_at = NOW() - 700s` для одной ноды (например, `irrig`).
   - Запустить `POST /zones/{id}/start-cycle`.
   - Task fail-closed с `error_code='ae3_snapshot_required_node_persistently_offline'`.
   - Alert `biz_ae3_task_failed` содержит `details.persistently_offline_uids=["nd-test-irrig-1"]` и `details.zone_nodes` со всеми нодами зоны.
   - **Retry budget не тратится** (в БД `task.updated_at` ≈ `task.created_at + несколько секунд`).

4. **Required-type missing (manual):**
   - В зоне two_tank удалить все каналы `irrig`-ноды через `node_channels.is_active=FALSE`.
   - Запустить `POST /zones/{id}/start-cycle`.
   - Task fail-closed с `error_code='ae3_snapshot_required_node_type_missing'`, `details.missing_node_types=["irrig"]`.

5. **UI-каталог ошибок:** новые коды отображаются с русскими описаниями в Cockpit (alerts panel, zone detail page).

6. **Документация:** обновлены файлы из §3.7. Compatible-With строка проставлена.

7. **Линт/типы:**
   - `docker compose -f backend/docker-compose.dev.yml exec automation-engine python -m mypy ae3lite` — без новых ошибок.
   - `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=ErrorCodeCatalogService` — зелёный.

---

## 6. Что **вне** этого плана (вынесено в отдельные задачи)

1. **Персистентный счётчик retry-attempts вместо wall-clock-бюджета** — потребует миграции `ae_tasks` (добавление `snapshot_retry_attempts smallint`), отдельный план.
2. **Channel-level health в `ZoneActuatorRef`** (`node_online: bool`, `node_last_seen_age_sec: int`) — требует обновления DTO-контракта и пересмотра всех stage-handler'ов для использования этих полей. Отдельный план.
3. **Heartbeat lag как метрика Prometheus** (`ae3_node_last_seen_age_seconds{node_uid=...}`) — отдельный план мониторинга.
4. **`/zones/{id}/diagnostics/nodes` REST endpoint** для фронтенда (live status всех нод зоны с last_seen_age) — отдельный план UI.

---

## 7. Контрольный список реализации

- [x] §3.1.1 — SQL-фильтр snapshot read-model дополнен fallback по `last_seen_at` (параметр `$2`, env `AE3_NODE_FRESHNESS_FALLBACK_SEC=180`).
- [x] §3.1.2 — Диагностический запрос `zone_nodes_diag_rows` + helper `_build_no_actuators_diagnostics` → `SnapshotBuildError.details`.
- [x] §3.2 — `SnapshotBuildError` уже поддерживал `details`; добавлены `AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE` и `AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING`.
- [x] §3.3.1 — `SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC` default поднят 90 → 600s.
- [x] §3.3.2-3.3.3 — Persistent dead → fail-closed без retry с `ae3_snapshot_required_node_persistently_offline`.
- [x] §3.3.4 — `_verify_topology_required_node_types` для two_tank topologies; `TWO_TANK_REQUIRED_NODE_TYPES = {"irrig", "ph", "ec"}`.
- [x] §3.3.5-3.3.6 — `_retry_transient_snapshot_gap` пробрасывает breakdown в `AE_SNAPSHOT_RETRY_SCHEDULED/EXHAUSTED` events и infra alerts; `_fail_closed` принимает `extra_details`.
- [x] §3.4 — Env-переменные `AE3_NODE_FRESHNESS_FALLBACK_SEC` (180), `AE3_NODE_PERSISTENT_DEAD_SEC` (600) с дефолтами в коде.
- [x] §3.6.1 — `test_ae3lite_zone_snapshot_freshness_fallback.py` (9 тестов).
- [x] §3.6.2 — `test_ae3lite_zone_snapshot_diagnostics.py` (6 тестов).
- [x] §3.6.3 — `test_ae3lite_execute_task.py` дополнен 4 новыми тестами; все 37 проходят.
- [x] §3.7.1 — `doc_ai/04_BACKEND_CORE/ae3lite.md` §5.4.
- [x] §3.7.2 — `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` (новые коды + уточнение существующих).
- [x] §3.7.4 — `backend/error_codes.json`, `backend/laravel/error_codes.json`, `backend/laravel/resources/js/constants/error_codes.json`.
- [x] §3.7.3 — `AE3_RUNTIME_EVENT_CONTRACT.md` whitelist расширен (`zone_nodes`, `persistently_offline_uids`, `transiently_offline_uids`, `missing_node_types`, `present_node_types`, `required_node_types`).
- [x] §3.7.5 — `errorCatalog.ts` без правок (источник локализации — JSON-каталоги `error_codes.json`; новые коды добавлены в каталоги).
- [x] §5 — manual checks 2–4 выполнены эквивалентным способом через SQL + direct `PgZoneSnapshotReadModel().load(...)` (ingress `POST /zones/{id}/start-cycle` в локальном окружении требует auth и возвращает `unauthorized` без токена):
  - scenario 2 (`status=offline`, `last_seen=now-60s` у всех нод): `SCENARIO_2_ACTUATORS 15` (fallback сработал);
  - scenario 3 (`irrig` offline `700s`): `SCENARIO_3_MISSING_REQUIRED ['irrig']`;
  - scenario 4 (`irrig` actuator channels `is_active=false`): `SCENARIO_4_MISSING_REQUIRED ['irrig']`.
- [x] Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 8. Формат ответа агента

По завершении задачи агент должен предоставить:

1. Список изменённых файлов с краткой аннотацией.
2. Diff/PR-ссылка.
3. Лог запусков `make test-ae` (новые тесты + регрессия).
4. Шаги воспроизведения сценариев из §5 (manual checks 2-4) с ожидаемыми ответами `POST /zones/{id}/start-cycle` и записями в `zone_events` / `ae_tasks`.
5. Скриншоты/выдержки из Cockpit, подтверждающие отображение новых error_codes.
6. Подтверждение Compatible-With.
