# AE3 Runtime Event Contract

**Дата:** 2026-04-10  
**Статус:** SOURCE OF TRUTH  

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

---

## 0. Назначение

Документ фиксирует канонический контракт runtime-событий AE3 для `zone_events`.

Цель:
- убрать неоднозначность между `details` и `payload_json`;
- зафиксировать обязательные поля для irrigation/correction observability;
- ввести versioned payload для безопасной эволюции e2e/read-model/UI.

## 1. Общие правила

1. Runtime-события AE3 читаются через канонический payload:
   `COALESCE(details, payload_json)`.
2. Для versioned AE3 runtime events обязателен `event_schema_version`.
3. Текущая каноническая версия runtime event payload:
   `event_schema_version = 2`.
4. Если event участвует в causal chain irrigation/correction, он обязан нести
   явные ссылки на родительский snapshot/event, а не только временную близость.

## 2. Обязательные общие поля

Для versioned irrigation/correction runtime events обязательны:

1. `event_schema_version`
2. `task_id`
3. `stage`
4. `current_stage`
5. `workflow_phase`

Допустимые дополнительные поля контекста:

1. `topology`
2. `correction_window_id`
3. `stage_entered_at`
4. `caused_by_event_id`
5. `snapshot_event_id`
6. `snapshot_created_at`
7. `snapshot_cmd_id`
8. `snapshot_source_event_type`

## 3. Causal Link Rules

### 3.1 Snapshot source

Для irrigation inline correction каноническим source event считается:

- `IRR_STATE_SNAPSHOT`

Если correction path подтверждён probe-state, downstream event должен ссылаться
на соответствующий `zone_events.id` через:

- `snapshot_event_id`

### 3.2 Downstream events

Для следующих событий `snapshot_event_id` обязателен, если correction decision/dose
происходит в `workflow_phase in ('irrigating', 'irrig_recirc')`:

1. `IRRIGATION_CORRECTION_STARTED`
2. `CORRECTION_DECISION_MADE`
3. `EC_DOSING`
4. `PH_CORRECTED`

Если `snapshot_event_id` присутствует, `caused_by_event_id` должен указывать на
тот же snapshot, если нет более специфичной causal-link ссылки.

## 4. Event-Specific Contract

### 4.1 `IRRIGATION_DECISION_SNAPSHOT_LOCKED`

Назначение:
- зафиксировать strategy/config/bundle_revision для irrigation task.

Обязательные поля:

1. `event_schema_version`
2. `task_id`
3. `zone_id`
4. `stage`
5. `current_stage`
6. `workflow_phase`
7. `strategy`

Условно обязательные поля:

1. `bundle_revision`
2. `config`
3. `grow_cycle_id`
4. `phase_name`

### 4.2 `IRRIGATION_CORRECTION_STARTED`

Назначение:
- отметить вход в correction path во время полива.

Обязательные поля:

1. `event_schema_version`
2. `task_id`
3. `stage`
4. `current_stage`
5. `workflow_phase`

Условно обязательные поля:

1. `snapshot_event_id`
2. `caused_by_event_id`

### 4.3 `CORRECTION_DECISION_MADE`

Назначение:
- записать итог decision window и выбранное действие.

Обязательные поля:

1. `event_schema_version`
2. `task_id`
3. `stage`
4. `current_stage`
5. `workflow_phase`
6. `selected_action`
7. `decision_reason`

Условно обязательные поля:

1. `needs_ec`
2. `needs_ph_up`
3. `needs_ph_down`
4. `snapshot_event_id`
5. `caused_by_event_id`

### 4.4 `EC_DOSING`

Назначение:
- зафиксировать факт EC dose и контекст, в котором он был выполнен.

Обязательные поля:

1. `event_schema_version`
2. `task_id`
3. `stage`
4. `current_stage`
5. `workflow_phase`
6. `node_uid`
7. `channel`
8. `duration_ms` или `amount_ml`

Условно обязательные поля:

1. `snapshot_event_id`
2. `caused_by_event_id`
3. `observe_seq`

### 4.5 `PH_CORRECTED`

Назначение:
- зафиксировать pH dosing path и причинную связь с snapshot/decision.

Обязательные поля:

1. `event_schema_version`
2. `task_id`
3. `stage`
4. `current_stage`
5. `workflow_phase`
6. `node_uid`
7. `channel`
8. `duration_ms` или `amount_ml`

Условно обязательные поля:

1. `snapshot_event_id`
2. `caused_by_event_id`
3. `observe_seq`

## 5. E2E / Read-Model Guidance

1. Новый e2e/assertion contract не должен доказывать причинность по `created_at`,
   если доступен `snapshot_event_id` или другой explicit causal link.
2. Для runtime event queries использовать:
   `COALESCE(details, payload_json)`.
3. Inline irrigation regression обязан проверять:
   - наличие `snapshot_event_id` у `EC_DOSING`;
   - существование связанного `IRR_STATE_SNAPSHOT`;
   - `pump_main=true` в payload связанного snapshot.

## 6. Evolution Rule

Если обязательные поля меняются несовместимо:

1. поднять `event_schema_version`;
2. обновить этот документ;
3. обновить e2e/read-model/UI контракт;
4. явно указать `Compatible-With`.
