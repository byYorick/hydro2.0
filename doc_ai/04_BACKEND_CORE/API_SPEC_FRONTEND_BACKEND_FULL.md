# API_SPEC_FRONTEND_BACKEND_FULL.md
# Полная детальная спецификация API между Frontend и Backend (2.0)
# **ОБНОВЛЕНО ПОСЛЕ МЕГА-РЕФАКТОРИНГА 2025-12-25**

Документ описывает REST и WebSocket-API, которые использует frontend (Web/Android)
для работы с системой 2.0.

**КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ПОСЛЕ РЕФАКТОРИНГА:**
- ✅ Новые эндпоинты для GrowCycle: `/api/grow-cycles/*`
- ✅ Удалены legacy эндпоинты: `/api/zones/*/attach-recipe`
- ✅ Новый internal API: `/api/internal/effective-targets/batch`
- ✅ Версионирование рецептов: `/api/recipe-revisions/*`

Задача документа:
- зафиксировать **контракты**;
- помочь ИИ-агентам не плодить несогласованные эндпоинты;
- обеспечить консистентную эволюцию API в рамках целевого Protocol 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общие принципы API

- Базовый префикс REST-API: `/api`.
- Все ответы — JSON.
- Аутентификация — token-based (например, `Authorization: Bearer <token>`).
- Валидация на backend → фронт получает структурированные ошибки.
- Локализация сообщений об ошибках — через стандартные механизмы Laravel.

### 1.1. Требования аутентификации

**Публичные эндпоинты** (не требуют аутентификации):
- `GET /api/system/health` - проверка здоровья сервиса
- `POST /api/python/ingest/telemetry` - инжест телеметрии (token-based)
- `POST /api/python/commands/ack` - подтверждение команд (token-based)
- `POST /api/alerts/webhook` - webhook от Alertmanager

**Service-token / служебные эндпоинты**:
- `GET /api/system/config/full` - полная конфигурация (middleware `verify.python.service`: Sanctum или service token)

**Защищенные эндпоинты** (требуют `auth:sanctum`):
- Все эндпоинты в разделах 3-7, 9-12 требуют аутентификации через Laravel Sanctum
- Раздел 2 (Auth): `POST /api/auth/logout` и `GET /api/auth/me` требуют аутентификации
- Раздел 8 (System): `GET /api/system/health` публичный, `GET /api/system/config/full` защищен `verify.python.service`
- Токен передается в заголовке: `Authorization: Bearer <token>`
- Токен получается через `POST /api/auth/login`

**Роли и права доступа**:
- `viewer` - только чтение данных
- `operator` - чтение + управление зонами, подтверждение алертов
- `agronomist` - управление grow-cycle и ревизиями рецептов
- `engineer` - инженерные операции и сервисные логи
- `admin` - полный доступ, включая управление пользователями

Стандартный формат ответа:

```json
{
 "status": "ok",
 "data": { }
}
```

Формат ошибок:

```json
{
 "status": "error",
 "message": "Invalid request",
 "code": 400,
 "errors": {
 "field": ["Error description"]
 }
}
```

---

## 2. Auth API

**Аутентификация:** Смешанная - `login` публичный, остальные требуют `auth:sanctum`.

### 2.1. POST /api/auth/login

- **Аутентификация:** Не требуется (публичный эндпоинт)
- Вход: `{ "email": " ", "password": " " }`
- Выход (успех):

```json
{
 "status": "ok",
 "data": {
 "token": " ",
 "user": {
 "id": 1,
 "name": "Operator",
 "roles": ["admin"]
 }
 }
}
```

### 2.2. POST /api/auth/logout

- **Аутентификация:** Требуется `auth:sanctum`
- Выход: `{"status": "ok"}`

### 2.3. GET /api/auth/me

- **Аутентификация:** Требуется `auth:sanctum`
- Возвращает текущего пользователя и его права.

---

## 3. Grow Cycles API (НОВОЕ после рефакторинга)

**Аутентификация:** `GET /api/zones/{zone}/grow-cycle` требует `auth:sanctum`; mutating-endpoint-ы grow-cycle требуют роль `agronomist` (дополнительно к route-level middleware).

**Центр API для управления циклами выращивания.**

### 3.1. GET /api/zones/{zone}/grow-cycle

- **Описание:** Получить активный цикл зоны с effective targets
- **Аутентификация:** Требуется `auth:sanctum`
- **Ответ:**
```json
{
  "status": "ok",
  "data": {
    "id": 123,
    "zone_id": 5,
    "plant": {"id": 1, "name": "Tomato"},
    "recipe_revision": {
      "id": 456,
      "recipe": {"name": "Standard Tomato"},
      "version": 2
    },
    "current_phase": {
      "id": 789,
      "name": "VEG",
      "started_at": "2025-01-01T10:00:00Z",
      "progress": 0.3
    },
    "status": "RUNNING",
    "effective_targets": {
      "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
      "ec": {"target": 1.5, "min": 1.3, "max": 1.7}
      // ... остальные цели
    }
  }
}
```

### 3.2. POST /api/zones/{zone}/grow-cycles

- **Описание:** Создать новый цикл выращивания
- **Тело запроса:**
```json
{
  "recipe_revision_id": 456,
  "plant_id": 1,
  "planting_at": "2025-01-01T08:00:00Z",
  "batch_label": "Batch 2025-001",
  "notes": "Test cycle"
}
```

### 3.3. POST /api/grow-cycles/{id}/pause

- **Описание:** Приостановить цикл

### 3.4. POST /api/grow-cycles/{id}/resume

- **Описание:** Возобновить цикл

### 3.5. POST /api/grow-cycles/{id}/set-phase

- **Описание:** Ручной переход на фазу
- **Тело:** `{"phase_index": 1, "comment": "Early transition due to plant health"}`

### 3.6. POST /api/grow-cycles/{id}/advance-phase

- **Описание:** Перейти на следующую фазу

### 3.7. POST /api/grow-cycles/{id}/change-recipe-revision

- **Описание:** Сменить ревизию рецепта
- **Тело:** `{"recipe_revision_id": 789, "apply_at_next_phase": true}`

### 3.8. POST /api/grow-cycles/{id}/harvest

- **Описание:** Завершить цикл сбором урожая
- **Тело:** `{"actual_harvest_at": "2025-02-01T12:00:00Z", "yield_kg": 15.5}`

---

## 4. Recipe Revisions API (НОВОЕ)

**Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`.

### 4.1. POST /api/recipes/{recipe}/revisions

- **Описание:** Создать новую ревизию из существующей
- **Тело:** `{"from_revision_id": 456, "description": "Optimized for summer conditions"}`

### 4.2. PATCH /api/recipe-revisions/{id}

- **Описание:** Редактировать DRAFT ревизию

### 4.3. POST /api/recipe-revisions/{id}/publish

- **Описание:** Опубликовать DRAFT ревизию

### 4.4. GET /api/recipe-revisions/{id}

- **Описание:** Получить ревизию с фазами

### 4.5. POST /api/recipe-revisions/{id}/phases

- **Описание:** Добавить фазу в ревизию рецепта

### 4.6. PATCH /api/recipe-revision-phases/{id}

- **Описание:** Обновить фазу ревизии рецепта

### 4.7. DELETE /api/recipe-revision-phases/{id}

- **Описание:** Удалить фазу ревизии рецепта

---

## 5. Internal API (для Python сервисов)

**Аутентификация:** Token-based (LARAVEL_API_TOKEN)

### 5.1. POST /api/internal/effective-targets/batch

- **Описание:** Batch получение effective targets для зон
- **Тело:** `{"zone_ids": [1, 2, 3]}`
- **Ответ:** Массив effective targets по зонам

#### Контракт scheduler-task execution (обязательная структура `targets.*.execution`)

`scheduler` и `automation-engine` используют `effective-targets.targets` как единый контракт
для task-level автоматизации.

Для каждого task типа допускаются ключи:

- `targets.irrigation`
- `targets.lighting`
- `targets.ventilation`
- `targets.solution_change`
- `targets.mist`
- `targets.diagnostics`

Каждый из этих объектов может содержать блок `execution`:

```json
{
  "execution": {
    "node_types": ["irrig"],
    "cmd": "run_pump",
    "cmd_true": "light_on",
    "cmd_false": "light_off",
    "state_key": "desired_state",
    "default_state": true,
    "params": {
      "state": true
    },
    "duration_sec": 120
  }
}
```

Правила:
- `node_types` (array<string>): типы нод для выполнения.
- `node_types` должны содержать только канонические значения `nodes.type`:
  `ph|ec|climate|irrig|light|relay|water_sensor|recirculation|unknown`.
- Legacy-алиасы (`irrigation`, `pump_node`, `climate_node`, `lighting_node` и т.п.) не допускаются.
- `cmd` (string): основная команда для task.
- `cmd_true`/`cmd_false` (string): команды для state-based task (например свет).
- `state_key` (string): имя поля в payload для выбора ветки `cmd_true/cmd_false`.
- `default_state` (bool): значение по умолчанию, если `state_key` не задан.
- `params` (object): дефолтные параметры команды.
- `duration_sec` (number): дефолтная длительность; нормализуется в `duration_ms` на стороне automation-engine.
- для `targets.diagnostics.execution` дополнительно допускаются startup-поля `2 бака`:
  - `workflow`: `startup|clean_fill_check|solution_fill_check|prepare_recirculation|prepare_recirculation_check|irrigation_recovery|irrigation_recovery_check`
  - `level_poll_interval_sec`
  - `clean_fill_timeout_sec`
  - `solution_fill_timeout_sec`
  - `prepare_recirculation_timeout_sec`
  - `irrigation_recovery.max_continue_attempts`
  - `irrigation_recovery.timeout_sec`
  - `target_ec_prepare_npk` (optional override для этапа prepare)
  - `nutrient_npk_ratio_pct` (optional override доли NPK, если не брать из `targets.nutrition.components.npk.ratio_pct`)

Правило расчёта prepare EC:
- `EC_prepare_npk = EC_target_total * nutrient_npk_ratio_pct / 100`
- если `target_ec_prepare_npk` передан явно, используется он;
- если доля NPK отсутствует, применяется безопасный fallback `nutrient_npk_ratio_pct=100` (поведение как у общего `EC target`).

Если `execution` отсутствует, используется встроенный mapping automation-engine.

#### Контракт scheduler-schedule (рекомендуемые поля в `targets`)

- `<task>.interval_sec` — интервальное расписание.
- `<task>.times` — массив времён `HH:MM`.
- `<task>_schedule` — альтернативный ключ расписания (строка, массив или объект с `times`).

Runtime-обновления из фронтового конфигуратора сохраняются в
`zone_automation_logic_profiles` через API `/api/zones/{zone}/automation-logic-profile`
и затем нормализуются в `effective_targets.targets` по тем же правилам
(`interval_minutes -> interval_sec`, `duration_seconds -> duration_sec`, `subsystems.diagnostics -> targets.diagnostics.execution`).

Команда применения runtime-профиля:
- `POST /api/zones/{zone}/commands` с `type=GROWTH_CYCLE_CONFIG`
- `params.mode` = `adjust|start`
- `params.profile_mode` = `setup|working`
- `params.subsystems` в команде не передаётся (инжектится сервером из `zone_automation_logic_profiles`)

Команда ручного override (операторский режим, `2 бака`):
- endpoint: `POST /api/zones/{zone}/commands`
- `type`: `GROWTH_CYCLE_CONFIG`
- `params.mode`: `adjust`
- `params.manual_action`:
  - `fill_clean_tank`
  - `prepare_solution`
  - `recirculate_solution`
  - `resume_irrigation`
- backend обязан логировать `manual_action` в `zone_events`/`scheduler_logs`.

### 5.2. POST /api/internal/realtime/telemetry-batch

- **Описание:** Batched realtime ingest телеметрии для WebSocket
- **Тело:**
```json
{
  "updates": [
    {
      "zone_id": 1,
      "node_id": 10,
      "channel": "ph_sensor",
      "metric_type": "PH",
      "value": 6.2,
      "timestamp": 1700000000000
    }
  ]
}
```
- **Ограничения:** `REALTIME_BATCH_MAX_UPDATES`, `REALTIME_BATCH_MAX_BYTES`
- **Ответ:** `{"status":"ok","broadcasted":1,"updates":1}`

---

## 6. Greenhouses / Zones / Nodes (ОБНОВЛЕНО)

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 3.1. GET /api/greenhouses

- **Аутентификация:** Требуется `auth:sanctum`
- Список теплиц с краткой информацией.

### 3.2. POST /api/greenhouses

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Создание теплицы.

### 3.3. GET /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация + связанные зоны.

### 3.3.1. PATCH /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Обновление теплицы.

### 3.3.2. DELETE /api/greenhouses/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление теплицы (если безопасно, нет связанных зон).

### 3.4. GET /api/zones

- **Аутентификация:** Требуется `auth:sanctum`
- Список зон (с фильтрами по теплице, статусу и т.п.).

### 3.5. GET /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Полная карточка зоны:
 - конфигурация;
 - активный рецепт и фаза;
 - привязанные узлы и каналы;
 - последние значения ключевых метрик.

### 3.5.1. GET /api/zones/{id}/scheduler-tasks

- **Аутентификация:** Требуется `auth:sanctum`
- **Описание:** Возвращает последние scheduler-task для зоны из `scheduler_logs`.
- **Параметры запроса:**
  - `limit` (1..100, default=20)
  - `include_timeline` (bool, default=false) — при `true` добавляет `timeline[]` из `zone_events` для каждого task.
- **Поля ответа:** `task_id`, `status`, `result`, `error`, `error_code`, `action_required`, `decision`, `reason_code`, `reason`, `executed_steps`, `safety_flags`, `next_due_at`, `measurements_before_after`, `run_mode`, `retry_attempt`, `retry_max_attempts`, `retry_backoff_sec`, `source`, `lifecycle[]`, `timeline[]`.
- **Lifecycle:** снимки статусов из `scheduler_logs` (типично `accepted/running/completed/failed`).
- **Timeline:** task-события из `zone_events` (`TASK_STARTED`, `DECISION_MADE`, `COMMAND_DISPATCHED`, `COMMAND_FAILED`, `TASK_FINISHED`, ...),
  фильтрация по `task_id` и/или `correlation_id`.
- **Сортировка timeline:** строго по времени события по возрастанию (`created_at ASC`, затем `id ASC`).
- **Инварианты контракта:** `correlation_id`, `due_at`, `expires_at` обязательны на уровне task-source (`automation-engine`).

### 3.5.2. GET /api/zones/{id}/scheduler-tasks/{taskId}

- **Аутентификация:** Требуется `auth:sanctum`
- **Описание:** Возвращает актуальный статус scheduler-task по `taskId`.
- **Поведение:** Laravel запрашивает `automation-engine /scheduler/task/{taskId}` без fallback на legacy-ветки.
- **Источник:** в `data.source` возвращается только `automation_engine`.
- **Дополнительно:** ответ всегда содержит:
  - `lifecycle[]` (снимки `scheduler_logs`);
  - `timeline[]` (детальные task-события из `zone_events`);
  - нормализованные outcome-поля: `action_required`, `decision`, `reason_code`, `reason`, `error_code`, `executed_steps`, `safety_flags`, `next_due_at`, `measurements_before_after`, `run_mode`, `retry_attempt`, `retry_max_attempts`, `retry_backoff_sec`.
- Для 2-бакового recovery перехода (`irrigation -> tank-to-tank`) в `result.*` используются:
  - `source_reason_code=online_correction_failed`
  - `transition_reason_code=tank_to_tank_correction_started`
  - `online_correction_error_code` (код исходной неуспешной online-коррекции).

### 3.5.3. GET /api/zones/{id}/automation-logic-profile

- **Аутентификация:** Требуется `auth:sanctum`
- **Описание:** Возвращает сохранённые профили логики автоматики для зоны (`setup`/`working`) и активный режим.
- **Ответ (`data`):**
  - `active_mode: \"setup\"|\"working\"|null`
  - `profiles.setup|profiles.working`:
    - `mode`
    - `is_active`
    - `subsystems` (runtime-конфиг подсистем)
    - `updated_at`

### 3.5.4. POST /api/zones/{id}/automation-logic-profile

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- **Описание:** Upsert профиля логики автоматики зоны.
- **Тело:**
  - `mode: \"setup\"|\"working\"`
  - `subsystems: object` (обязательны `ph/ec/irrigation`, enabled=true)
  - `activate: bool` (optional, default=true)
- **Эффект:** при `activate=true` профиль переводится в активный runtime-режим для `effective_targets`.
- **Валидация:** поля `subsystems.*.targets` запрещены (HTTP `422`), допускается только `subsystems.*.execution`.

Минимальные поля `subsystems` для `2 бака`:
- `subsystems.diagnostics.execution.topology = \"two_tank_drip_substrate_trays\"`
- `subsystems.diagnostics.execution.startup.clean_fill_timeout_sec` (default `1200`)
- `subsystems.diagnostics.execution.startup.solution_fill_timeout_sec` (default `1800`)
- `subsystems.diagnostics.execution.startup.level_poll_interval_sec` (default `60`)
- `subsystems.diagnostics.execution.startup.clean_fill_retry_cycles` (default `1`)
- `subsystems.diagnostics.execution.startup.prepare_recirculation_timeout_sec` (default `1200`)
- `subsystems.irrigation.recovery.max_continue_attempts` (default `5`)
- `subsystems.irrigation.recovery.degraded_tolerance.ec_pct` (default `20`)
- `subsystems.irrigation.recovery.degraded_tolerance.ph_pct` (default `10`)
- `subsystems.diagnostics.execution.dosing_rules.prepare_allowed_components = [\"npk\"]`
- `subsystems.irrigation.dosing_rules.irrigation_allowed_components = [\"calcium\", \"magnesium\", \"micro\"]`
- `subsystems.irrigation.dosing_rules.irrigation_forbid_components = [\"npk\"]`

Ограничение:
- recipe-targets (`ph/ec/...`) не сохраняются в logic-profile.

Условная обязательность:
- при `subsystems.diagnostics.execution.topology = \"two_tank_drip_substrate_trays\"`
  обязательны оба блока: `subsystems.diagnostics` и `subsystems.irrigation`.

### 3.6. POST /api/zones

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Создание зоны.

### 3.7. PATCH /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Обновление параметров зоны (название, тип, лимиты и т.п.).

### 3.7.1. DELETE /api/zones/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Удаление зоны (если нет активных зависимостей).

### 3.8. GET /api/nodes

- **Аутентификация:** Требуется `auth:sanctum`
- Список узлов ESP32, их статус (online/offline), привязка к зонам.

### 3.9. GET /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация об узле:
 - NodeConfig;
 - список каналов;
 - последняя телеметрия.

### 3.9.1. POST /api/nodes

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Регистрация нового узла ESP32.

### 3.9.2. PATCH /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Обновление метаданных узла (name, zone_id).

### 3.9.3. DELETE /api/nodes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Удаление узла.

### 3.9.4. GET /api/nodes/{id}/config

- **Аутентификация:** Требуется `auth:sanctum`
- Получение сохраненного NodeConfig (read-only), полученного от ноды через `config_report`.

Ответ:
```json
{
 "status": "ok",
 "data": {
   "node_uid": "nd-001",
   "zone_id": 1,
   "channels": [...],
   "settings": {...}
 }
}
```

### 3.9.5. POST /api/nodes/{id}/config/publish

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Публикация конфигурации узла через MQTT **отключена**.
- Узлы отправляют конфиг самостоятельно (config_report), сервер хранит и использует его.

Ответ:
```json
{
 "status": "error",
 "message": "Config publishing from server is disabled. Nodes send config_report on connect."
}
```

### 3.9.6. POST /api/nodes/{id}/swap

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Замена узла новым узлом с миграцией данных.

Тело запроса:
```json
{
 "new_hardware_id": "ESP32-ABC123",
 "migrate_telemetry": true,
 "migrate_channels": true
}
```

Ответ:
```json
{
 "status": "ok",
 "data": {
   "old_node_id": 1,
   "new_node_id": 2,
   "migrated_telemetry_count": 1000,
   "migrated_channels_count": 4
 }
}
```

### 3.9.7. POST /api/setup-wizard/validate-devices

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator`, `admin`, `agronomist`, `engineer`
- Серверная валидация шага `4. Устройства` в мастере настройки.
- Проверяет:
 - обязательные роли (`irrigation`, `ph_correction`, `ec_correction`, `accumulation`) заполнены;
 - обязательные роли назначены на разные ноды;
 - ноды доступны пользователю и не привязаны к другой зоне;
 - выбранные ноды соответствуют ожидаемой роли по `type`/`channels`.

Тело запроса:
```json
{
  "zone_id": 12,
  "assignments": {
    "irrigation": 101,
    "ph_correction": 102,
    "ec_correction": 104,
    "accumulation": 103,
    "climate": null,
    "light": null
  },
  "selected_node_ids": [101, 102, 104, 103]
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "validated": true,
    "zone_id": 12,
    "required_roles": {
      "irrigation": 101,
      "ph_correction": 102,
      "ec_correction": 104,
      "accumulation": 103
    }
  }
}
```

### 3.9.8. POST /api/setup-wizard/apply-device-bindings

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator`, `admin`, `agronomist`, `engineer`
- Применение шага `4. Устройства`:
 - повторная серверная валидация назначения ролей;
 - привязка ролей инфраструктуры зоны к каналам выбранных нод;
 - для обязательных ролей создаются/обновляются bind-ы:
   `main_pump`, `drain`, `ph_acid_pump`, `ph_base_pump`,
   `ec_npk_pump`, `ec_calcium_pump`, `ec_magnesium_pump`, `ec_micro_pump`;
 - для опциональных ролей, при наличии, создаются bind-ы `vent`, `heater`, `light`.

Тело запроса:
```json
{
  "zone_id": 12,
  "assignments": {
    "irrigation": 101,
    "ph_correction": 102,
    "ec_correction": 104,
    "accumulation": 103,
    "climate": 105,
    "light": 106
  },
  "selected_node_ids": [101, 102, 104, 103, 105, 106]
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "validated": true,
    "zone_id": 12,
    "required_roles": {
      "irrigation": 101,
      "ph_correction": 102,
      "ec_correction": 104,
      "accumulation": 103
    },
    "applied_bindings": [
      {
        "assignment_role": "irrigation",
        "binding_role": "main_pump",
        "node_id": 101,
        "node_uid": "nd-test-irrig-1",
        "channel_id": 2001
      }
    ]
  }
}
```

---

## 4. Recipes API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 4.1. GET /api/recipes

- **Аутентификация:** Требуется `auth:sanctum`
- Список рецептов (фильтры по типу культур, активности).

### 4.2. POST /api/recipes

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Создание рецепта и базового набора фаз.

### 4.3. GET /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальное описание рецепта + фазы.

### 4.4. PATCH /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Обновление рецепта (описание, культура и т.п.).

### 4.4.1. DELETE /api/recipes/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `admin`
- Удаление рецепта.

### 4.5. POST /api/recipes/{recipe}/revisions

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Создание новой DRAFT-ревизии рецепта.

### 4.6. PATCH /api/recipe-revisions/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Обновление DRAFT-ревизии.

### 4.6.1. POST /api/recipe-revisions/{id}/publish

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Публикация DRAFT-ревизии.

### 4.6.2. GET /api/recipe-revisions/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Получение ревизии рецепта с фазами.

### 4.6.3. POST /api/recipe-revisions/{id}/phases

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Добавление фазы ревизии рецепта.

### 4.6.4. PATCH /api/recipe-revision-phases/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Обновление фазы ревизии.

### 4.6.5. DELETE /api/recipe-revision-phases/{id}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Удаление фазы ревизии.

### 4.7. POST /api/zones/{zone}/grow-cycles

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Создание нового grow cycle для зоны.

### 4.8. POST /api/grow-cycles/{growCycle}/set-phase

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Ручной переход фазы grow cycle.

### 4.9. POST /api/grow-cycles/{growCycle}/pause

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Приостановка grow cycle.

### 4.10. POST /api/grow-cycles/{growCycle}/resume

- **Аутентификация:** Требуется `auth:sanctum`, роль `agronomist`
- Возобновление grow cycle.

### 4.11. GET /api/zones/{id}/cycles

- **Аутентификация:** Требуется `auth:sanctum`
- Получение информации о циклах зоны (PH_CONTROL, EC_CONTROL, IRRIGATION, LIGHTING, CLIMATE).

Ответ:
```json
{
 "status": "ok",
 "data": {
   "PH_CONTROL": {
     "type": "PH_CONTROL",
     "strategy": "periodic",
     "interval": 300,
     "last_run": "2025-11-17T10:00:00Z",
     "next_run": "2025-11-17T10:05:00Z"
   },
   "EC_CONTROL": {
     "type": "EC_CONTROL",
     "strategy": "periodic",
     "interval": 300,
     "last_run": null,
     "next_run": null
   },
   "IRRIGATION": {
     "type": "IRRIGATION",
     "strategy": "periodic",
     "interval": 3600,
     "last_run": "2025-11-17T09:00:00Z",
     "next_run": "2025-11-17T10:00:00Z"
   },
   "LIGHTING": {
     "type": "LIGHTING",
     "strategy": "periodic",
     "interval": 43200,
     "last_run": null,
     "next_run": null
   },
   "CLIMATE": {
     "type": "CLIMATE",
     "strategy": "periodic",
     "interval": 300,
     "last_run": "2025-11-17T09:55:00Z",
     "next_run": "2025-11-17T10:00:00Z"
   }
 }
}
```

---

## 5. Telemetry & History API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 5.1. GET /api/zones/{id}/telemetry/last

- **Аутентификация:** Требуется `auth:sanctum`
- Последние значения ключевых метрик по зоне.

### 5.2. GET /api/zones/{id}/telemetry/history

- **Аутентификация:** Требуется `auth:sanctum`
- Параметры:
  - `metric` — например, `PH`, `EC`, `TEMPERATURE`;
  - `from`, `to` — временной диапазон.
- Ответ — массив точек для графика.

### 5.3. GET /api/nodes/{id}/telemetry/last

- **Аутентификация:** Требуется `auth:sanctum`
- Последняя телеметрия по канальным метрикам узла.

---

## 6. Commands API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`, роль `operator`, `admin`, `agronomist` или `engineer`.

### 6.1. POST /api/zones/{id}/commands

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator`, `admin`, `agronomist` или `engineer`
- **Валидация:** Используется `StoreZoneCommandRequest` для валидации входных данных
- **Авторизация:** Проверка прав через `ZonePolicy::sendCommand`
- **HMAC подпись:** Команды автоматически подписываются HMAC с timestamp перед отправкой в Python-сервис
- Отправка команд на зону (через Python-сервис).
- Примеры команд:
 - `FORCE_IRRIGATION` - принудительный полив (требует `params.duration_sec`);
 - `FORCE_DRAIN` - принудительный дренаж;
 - `FORCE_PH_CONTROL` - принудительный контроль pH;
 - `FORCE_EC_CONTROL` - принудительный контроль EC;
 - `FORCE_LIGHTING` - принудительное управление освещением;
 - `FORCE_CLIMATE` - принудительное управление климатом;
 - `FORCE_LIGHT_ON/OFF` - включение/выключение света (устаревшая, используйте `FORCE_LIGHTING`);
 - `ZONE_PAUSE/RESUME` - legacy-команды управления зоной (предпочтителен lifecycle через grow-cycle endpoints).

Тело запроса:

```json
{
 "type": "FORCE_IRRIGATION",
 "params": {
 "duration_sec": 30
 }
}
```

Ответ:

```json
{
 "status": "ok",
 "data": {
 "command_id": "cmd- "
 }
}
```

### 6.2. POST /api/nodes/{id}/commands

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator`, `admin`, `agronomist` или `engineer`
- **Валидация:** Используется `StoreNodeCommandRequest` для валидации входных данных
- **Авторизация:** Проверка прав через `DeviceNodePolicy::sendCommand`
- **HMAC подпись:** Команды автоматически подписываются HMAC с timestamp перед отправкой в Python-сервис
- Низкоуровневые команды для конкретного узла (диагностика, калибровка).

---

## 7. Alerts & Events API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 7.1. GET /api/alerts

- **Аутентификация:** Требуется `auth:sanctum`
- Список активных/исторических алертов.

### 7.2. GET /api/alerts/{id}

- **Аутентификация:** Требуется `auth:sanctum`
- Детальная информация об алерте.

### 7.3. PATCH /api/alerts/{id}/ack

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator`, `admin`, `agronomist` или `engineer`
- Подтверждение алерта оператором.

### 7.4. GET /api/alerts/stream

- **Аутентификация:** Требуется `auth:sanctum`
- Server-Sent Events поток алертов для realtime обновлений.

---

## 8. System API

### 8.1. GET /api/system/config/full

- **Аутентификация:** `verify.python.service` (Sanctum или service token)
- Полная конфигурация теплиц/зон/узлов/каналов для Python/AI.

### 8.2. GET /api/system/health

- **Аутентификация:** Публичный эндпоинт
- Проверка здоровья сервиса.

---

## 9. Presets API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 9.1. GET /api/presets

- Список пресетов (шаблонов конфигураций).

### 9.2. POST /api/presets

- Создание нового пресета.

### 9.3. GET /api/presets/{id}

- Детальная информация о пресете.

### 9.4. PATCH /api/presets/{id}

- Обновление пресета.

### 9.5. DELETE /api/presets/{id}

- Удаление пресета.

---

## 10. Reports & Analytics API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 10.1. GET /api/recipes/{id}/analytics

- Аналитика по рецепту (статистика, эффективность, урожайность).

### 10.2. GET /api/zones/{id}/harvests

- История урожаев по зоне.

### 10.3. POST /api/harvests

- Регистрация нового урожая.

Тело запроса:
```json
{
  "zone_id": 1,
  "crop": "Tomato",
  "weight_kg": 15.5,
  "harvested_at": "2025-01-15T10:00:00Z",
  "notes": "First harvest of the season"
}
```

### 10.4. POST /api/recipes/comparison

- Сравнение нескольких рецептов по метрикам.

---

## 11. AI API

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 11.1. POST /api/ai/predict

- Прогнозирование параметров для зоны.

Тело запроса:
```json
{
  "zone_id": 1,
  "metric_type": "PH",
  "horizon_minutes": 60
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "predicted_value": 6.2,
    "confidence": 0.85,
    "predicted_at": "2025-01-15T11:00:00Z",
    "horizon_minutes": 60
  }
}
```

### 11.2. POST /api/ai/explain_zone

- Объяснение текущего состояния зоны (AI анализ).

### 11.3. POST /api/ai/recommend

- Получение рекомендаций AI по оптимизации зоны.

### 11.4. POST /api/ai/diagnostics

- Запуск диагностики системы (анализ телеметрии, событий, выявление проблем).

---

## 12. Simulations API (Digital Twin)

**Аутентификация:** Все эндпоинты требуют `auth:sanctum`.

### 12.1. POST /api/simulations/zone/{zone}

- **Аутентификация:** Требуется `auth:sanctum`, роль `operator` или `admin` или `agronomist` или `engineer`
- Запуск симуляции Digital Twin для зоны.
  - `full_simulation` (bool, optional) — выполнить полный цикл с созданием сущностей и отчетом.

Тело запроса:
```json
{
  "scenario": "optimize_ph",
  "duration_hours": 24,
  "parameters": {
    "target_ph": 6.5
  },
  "full_simulation": false
}
```

### 12.2. GET /api/simulations/{job_id}

- **Аутентификация:** Требуется `auth:sanctum`
- Получение статуса симуляции (job), прогресса и отчета.

Ответ:
```json
{
  "status": "ok",
  "data": {
    "status": "processing",
    "simulation_id": 55,
    "report": {
      "id": 12,
      "simulation_id": 55,
      "zone_id": 12,
      "status": "completed",
      "started_at": "2026-01-26T09:10:00Z",
      "finished_at": "2026-01-26T09:11:00Z",
      "summary_json": { "simulation_zone_id": 99 },
      "phases_json": [],
      "metrics_json": { "phases_count": 3 },
      "errors_json": null
    }
  }
}
```

### 12.3. GET /api/simulations/{simulation}/events

- **Аутентификация:** Требуется `auth:sanctum`
- Возвращает события процесса симуляции (этапы, статусы, ошибки).

Параметры запроса (query):
```
limit (1..200, default 100)
order (asc|desc, default asc)
service (string)
stage (string)
status (string)
level (info|warning|error)
after_id (int)
since (ISO8601 date/time)
```

Ответ:
```json
{
  "status": "ok",
  "data": [
    {
      "id": 101,
      "simulation_id": 55,
      "zone_id": 12,
      "service": "digital-twin",
      "stage": "live_start",
      "status": "completed",
      "level": "info",
      "message": "Live-симуляция запущена",
      "payload": { "node_sim_session_id": "sim-12-1700000000" },
      "occurred_at": "2026-01-26T09:10:00Z",
      "created_at": "2026-01-26T09:10:00Z"
    }
  ],
  "meta": {
    "limit": 100,
    "order": "asc",
    "last_id": 101
  }
}
```

### 12.4. GET /api/simulations/{simulation}/events/stream

- **Аутентификация:** Требуется `auth:sanctum`
- SSE-стрим новых событий симуляции.

Параметры запроса (query):
```
last_id (int)
service (string)
stage (string)
status (string)
level (info|warning|error)
```

События приходят с именем `simulation_event`.

---

## 13. WebSocket / Realtime

Для realtime-обновлений используется **Laravel Reverb** (встроенный WebSocket сервер).

**Подключение:**
- WebSocket endpoint: `ws://localhost:6001` (или `wss://` для HTTPS)
- Используется библиотека `laravel-echo` и `pusher-js` на клиенте
- Аутентификация через тот же токен, что и REST API

**Основные каналы:**

- `hydro.zones.{id}` — обновления по зоне (`ZoneUpdated`, `NodeConfigUpdated`, `TelemetryBatchUpdated`);
- `hydro.alerts` — новые алерты (событие `AlertCreated`);
- `hydro.devices` — обновления устройств без зоны (fallback для `NodeConfigUpdated`).

**Формат событий:**
```json
{
  "event_type": "zone_state_updated",
  "event_id": "uuid-123",
  "occurred_at": "2025-01-15T12:00:00Z",
  "payload": {
    "zone_id": 1,
    "metrics": { "ph": 6.2, "ec": 1.8 }
  }
}
```

Подробнее см. `REALTIME_UPDATES_ARCH.md`.

---

## 13. Node Registration API

**Аутентификация:** Токен-базированная (service token), не требует `auth:sanctum`.

### 13.1. POST /api/nodes/register

- **Аутентификация:** Требуется service token (Bearer token) или IP whitelist
- **Rate Limiting:** Максимум 10 запросов в минуту по IP
- **IP Whitelist:** Настраивается через `services.node_registration.allowed_ips` (поддержка CIDR)
- **Валидация:** Используется `RegisterNodeRequest` для валидации входных данных
- Регистрация нового узла ESP32 в системе.

**Безопасность:**
- Обязательная проверка токена (если настроен)
- Rate limiting по IP (10 запросов/минуту)
- IP whitelist (если настроен)
- Защита от дублирования через уникальные ограничения в БД

Тело запроса (node_hello):
```json
{
  "message_type": "node_hello",
  "hardware_id": "ESP32-ABC123",
  "node_type": "ph",
  "fw_version": "2.0.1",
  "hardware_revision": "v1.0",
  "capabilities": {...},
  "provisioning_meta": {...}
}
```

Тело запроса (обычная регистрация):
```json
{
  "node_uid": "nd-001",
  "firmware_version": "2.0.1",
  "hardware_revision": "v1.0",
  "hardware_id": "ESP32-ABC123",
  "name": "pH Sensor Node",
  "type": "ph"
}
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "id": 1,
    "uid": "nd-001",
    "name": "pH Sensor Node",
    "type": "ph",
    "status": "offline",
    "lifecycle_state": "REGISTERED_BACKEND"
  }
}
```

---

## 14. Правила для ИИ-агентов

1. Все новые эндпоинты должны описываться здесь и в `REST_API_REFERENCE.md`.
2. Нельзя менять сигнатуру существующих эндпоинтов без явного указания версии (например, `/api/v2/`).
3. Все действия, влияющие на железо, должны проходить через Python-сервис (не ходить напрямую в MQTT из backend).
4. При добавлении нового эндпоинта обязательно указать требования аутентификации.
5. Публичные эндпоинты должны быть явно помечены как таковые.
6. Все мутирующие операции должны использовать FormRequest для валидации и Policy для авторизации.
7. Критичные операции (публикация конфигов, регистрация узлов) должны использовать блокировки и дедупликацию.

Этот документ задаёт **единый контракт** между UI и backend и служит опорой для дальнейшего развития системы.
