# AE3 IRR Level-Switch Event Contract

**Версия:** 1.1
**Дата:** 2026-04-09
**Статус:** Детализирующий контракт для AE3 / history-logger

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать, как canonical AE3 runtime и backend ingest трактуют channel-level события
дискретных датчиков уровня от `storage_irrigation_node`.

Документ не заменяет:
- `ae3lite.md` как канонический runtime-spec;
- `../03_TRANSPORT_MQTT/*` как transport/source-of-truth для MQTT payload/topology.

Документ уточняет только integration-contract:
- какие события публикует IRR-нода;
- что из них должен сохранять `history-logger`;
- как AE3 может использовать эти события как fast-path hint без нарушения DB-first модели.

---

## 2. Scope

Контракт относится только к production two-tank IRR-контуру:
- firmware: `storage_irrigation_node`;
- topology: `two_tank`;
- level channels:
  - `level_clean_min`
  - `level_clean_max`
  - `level_solution_min`
  - `level_solution_max`

Вне scope:
- generic event-bus для всех нод;
- изменение protected command pipeline;
- direct MQTT subscribe из AE3;
- замена reconcile polling на event-driven-only execution.

---

## 3. Источники истины

Transport/source-of-truth:
- `../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`

Runtime/source-of-truth:
- `ae3lite.md`
- `PYTHON_SERVICES_ARCH.md`
- `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`

Ключевой инвариант:
- MQTT event является fast-path signal, но не финальным source of truth для stage transition;
- canonical runtime state для AE3 остаётся в PostgreSQL (`telemetry_last`, `zone_events`, `zone_workflow_state`, `commands`);
- любое решение AE3 должно подтверждаться DB read-model / reconcile path.

---

## 4. Producer Contract

### 4.1 Channel-level event

IRR-нода публикует событие в топик:

```text
hydro/{gh}/{zone}/{node}/{channel}/event
```

где `{channel}` один из:
- `level_clean_min`
- `level_clean_max`
- `level_solution_min`
- `level_solution_max`

Payload:

```json
{
  "event_code": "level_switch_changed",
  "channel": "level_solution_min",
  "state": true,
  "initial": false,
  "ts": 1710012929,
  "snapshot": {
    "clean_level_min": true,
    "clean_level_max": false,
    "solution_level_min": true,
    "solution_level_max": false,
    "pump_main": false,
    "valve_clean_fill": false,
    "valve_clean_supply": false,
    "valve_solution_fill": false,
    "valve_solution_supply": false,
    "valve_irrigation": false
  }
}
```

Семантика:
- `state=true` означает, что датчик сработал;
- `state=false` означает, что датчик не сработал;
- событие публикуется на оба перехода: `0 -> 1` и `1 -> 0`;
- `state` уже debounce-подтверждён на стороне firmware;
- `snapshot` — это текущий `IRR_STATE_SNAPSHOT`, а не только состояние одного датчика.

### 4.2 Initial-state publication

После boot или MQTT reconnect нода обязана:
- дождаться time sync;
- опубликовать по одному событию на каждый `level_*` канал;
- проставить `initial=true`.

Важно:
- `initial=true` означает "текущее подтверждённое состояние после входа в online-session";
- это не гарантированный physical edge и не доказательство, что переход произошёл в данный момент.

### 4.3 Aggregate two-tank events

Параллельно сохраняется существующий aggregate-channel:

```text
hydro/{gh}/{zone}/{node}/storage_state/event
```

С кодами:
- `clean_fill_completed`
- `solution_fill_completed`
- `solution_fill_timeout`
- `prepare_recirculation_timeout`

Эти события не заменяются `level_switch_changed`.

---

## 5. History-Logger Contract

`history-logger` обязан:

1. Принимать оба event-потока:
   - `.../{level_*}/event`
   - `.../storage_state/event`
2. Нормализовывать `event_code` в `zone_events.type`.
3. Сохранять исходный payload в `zone_events.payload_json`.
4. Для `level_switch_changed` не терять поля:
   - `channel`
   - `state`
   - `initial`
   - `snapshot`
   - `ts`
5. Продолжать запись scalar telemetry в:
   - `telemetry_samples`
   - `telemetry_last`
6. Не трактовать channel-level event как замену telemetry ingest.
7. После успешной вставки node runtime event публиковать PostgreSQL `NOTIFY ae_zone_event`
   с нормализованным payload (`zone_id`, `event_type`, `channel`, `state`, `initial`, `snapshot`, ...),
   чтобы AE3 мог сделать `worker.kick()` без прямого доступа к MQTT.

Нормализованный `zone_events.type` для channel-level события:

```text
LEVEL_SWITCH_CHANGED
```

Рекомендуемые поля `payload_json`:

```json
{
  "event_code": "level_switch_changed",
  "channel": "level_clean_max",
  "state": true,
  "initial": false,
  "snapshot": { "...": "..." },
  "ts": 1710012930
}
```

---

## 6. AE3 Runtime Contract

### 6.1 Общий принцип

AE3 не подписывается на MQTT напрямую.

Разрешённый путь потребления сигнала:

`ESP32 -> MQTT -> history-logger -> PostgreSQL -> AE3`

AE3 может использовать `level_switch_changed` только как:
- fast-path hint для ускоренного wake-up / reconcile;
- вспомогательный observability signal;
- источник контекстного `snapshot` для логирования и timeline UI.

AE3 не может использовать `level_switch_changed` как единственное основание для:
- terminal stage completion;
- mutation `zone_workflow_state`;
- skip safety-checks;
- пропуска polling/reconcile.

### 6.2 Runtime read-model

После получения или обнаружения `level_switch_changed` AE3 обязан принимать решение только
после чтения актуального DB snapshot, минимум из:
- `telemetry_last`
- `zone_events`
- `zone_workflow_state`
- при необходимости `commands`

Каноническое правило:
- event будит runtime;
- runtime перечитывает read-model;
- переход выполняется только если read-model подтверждает допустимый state.

### 6.3 Семантика `initial=true`

`initial=true` для AE3 означает:
- online-session started;
- доступно свежее observed state датчика;
- можно немедленно выполнить reconcile.

`initial=true` не означает:
- что произошёл новый физический edge;
- что stage completion только что наступил;
- что можно повторно завершить уже terminal stage.

AE3 обязан обрабатывать `initial=true` идемпотентно.

Рекомендуемая и реализованная политика:
- для active stage-path `initial=true` используется как wake-up/observability signal;
- auto-reset `ready -> idle/startup` по `solution_min=false` может использовать `initial=true`,
  если depletion подтверждён каноническим DB read-model.

### 6.4 Что может делать AE3

AE3 может:
- ускорить polling loop / `worker.kick()` по новому `zone_event`;
- выполнить `ready/startup guard` сразу после `LEVEL_SWITCH_CHANGED` с `solution_min=false`;
- сократить latency между срабатыванием датчика и reconcile;
- использовать `payload_json.snapshot` как дополнительный observability artifact;
- отображать событие в timeline execution/task UI.

AE3 не должен:
- завершать `solution_fill` только по `LEVEL_SWITCH_CHANGED` без проверки read-model;
- считать `initial=true` эквивалентом stage-complete;
- заменять `clean_fill_completed` и `solution_fill_completed` на channel-level events.

---

## 7. Stage-Level Interpretation

### 7.1 `level_clean_max`

`level_clean_max/state=true` может быть ранним сигналом для AE3, что бак чистой воды достиг верхнего уровня.

Но canonical completion signal для stage остаётся:
- `storage_state/event` с `event_code=clean_fill_completed`
  или
- reconcile read-model, подтверждающий ожидаемое terminal state.

### 7.2 `level_solution_max`

`level_solution_max/state=true` может разбудить AE3 раньше periodic poll.

Но canonical stage-complete signal остаётся:
- `storage_state/event` с `event_code=solution_fill_completed`
  или
- reconcile по read-model.

### 7.3 `level_solution_min`

Этот канал важен для coarse-level readiness / наличия раствора.

Если read-model больше не подтверждает наличие раствора (`state=false`), AE3/runtime path может:
- auto-reset `zone_workflow_state` в `idle/startup` по правилам `ae3lite.md`;
- заблокировать дальнейший полив до нового `cycle_start`.

Решение принимается только после reconcile read-model, а не по одному event payload.

### 7.4 `level_clean_min`

Используется как сигнал уровня бака чистой воды и как дополнительный fast-path trigger для observability/reconcile.

Отдельного terminal stage-смысла сам по себе не задаёт.

---

## 8. Idempotency и delivery model

AE3 и backend обязаны исходить из at-least-once модели доставки:
- дубликаты MQTT/event возможны;
- repeated insert в `zone_events` возможен на уровне transport retries;
- reconnect вызывает повторный initial-state publish.

Следствия:
- обработка `level_switch_changed` должна быть идемпотентной;
- `initial=true` после reconnect не должен повторно завершать stage;
- channel-level event не должен создавать ложный business outcome без DB confirmation.

---

## 9. Observability

Минимум для timeline / debugging:
- channel-level `LEVEL_SWITCH_CHANGED`
- aggregate `CLEAN_FILL_COMPLETED`
- aggregate `SOLUTION_FILL_COMPLETED`
- aggregate `SOLUTION_FILL_TIMEOUT`
- aggregate `PREPARE_RECIRCULATION_TIMEOUT`

Рекомендуемое использование в UI/trace:
- `level_switch_changed` показывает физический сигнал датчика;
- `storage_state/event` показывает доменный outcome stage;
- вместе они позволяют видеть задержку между sensor edge и AE3 stage transition.

---

## 10. Acceptance Contract

Контракт считается выполненным, если:

1. IRR-нода публикует `level_switch_changed` в `.../{level_*}/event`.
2. После reconnect публикуется ровно один initial-state event на канал в рамках новой online-session.
3. `history-logger` сохраняет эти события в `zone_events`.
4. AE3 может использовать их как fast-path wake-up signal.
5. AE3 не нарушает DB-first модель и не принимает terminal stage decision только по event payload.
6. Existing `storage_state/event` контракты не ломаются и продолжают использоваться как domain events двухбакового workflow.

---

## 11. Связанные документы

- `ae3lite.md`
- `PYTHON_SERVICES_ARCH.md`
- `../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `../02_HARDWARE_FIRMWARE/STORAGE_IRRIGATION_NODE_PROD_SPEC.md`
