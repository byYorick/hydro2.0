# REST_API_REFERENCE.md
# Полный референс REST API для системы 2.0

Документ служит **справочником** по основным REST-эндпоинтам Laravel-backend,
которые используются фронтендом, Android и Python-сервисом (частично).

Он дополняет `API_SPEC_FRONTEND_BACKEND_FULL.md`, но сфокусирован именно на списке URL и их назначении.

Актуализация authority / AE3 (2026-03-24):
- единый запуск workflow через `POST /zones/{id}/start-cycle` (внутренний AE endpoint);
- legacy `POST /scheduler/task` и `GET /scheduler/task/{task_id}` удалены;
- runtime path automation-engine использует direct SQL read-model.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Auth

| Метод | Путь | Auth | Описание |
|-------|---------------------|------|-----------------------------------|
| POST | /api/auth/login | public | Вход, выдача токена |
| POST | /api/auth/logout | auth:sanctum | Выход, отзыв токена |
| GET | /api/auth/me | auth:sanctum | Инфо о текущем пользователе |

---

## 2. Greenhouses

| Метод | Путь | Auth | Описание |
|-------|-------------------------|------|-------------------------------|
| GET | /api/greenhouses | auth:sanctum | Список теплиц |
| POST | /api/greenhouses | auth:sanctum (operator/admin/agronomist/engineer) | Создать теплицу |
| GET | /api/greenhouses/{id} | auth:sanctum | Детали теплицы |
| PATCH | /api/greenhouses/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить теплицу |
| DELETE| /api/greenhouses/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить (если безопасно) |

---

## 3. Zones

| Метод | Путь | Auth | Описание |
|-------|-----------------------|------|------------------------------------------------|
| GET | /api/zones | auth:sanctum | Список зон (фильтры по теплице, статусу) |
| POST | /api/zones | auth:sanctum (operator/admin/agronomist/engineer) | Создать зону |
| GET | /api/zones/{id} | auth:sanctum | Детали зоны + активный рецепт |
| PATCH | /api/zones/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить параметры зоны, включая `automation_runtime=ae3` |
| DELETE| /api/zones/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить зону (если нет активных зависимостей) |

Доп. действия:

| Метод | Путь | Auth | Описание |
|-------|-----------------------------------|------|------------------------------------|
| POST | /api/zones/{id}/fill | auth:sanctum (operator/admin/agronomist/engineer) | Режим наполнения зоны |
| POST | /api/zones/{id}/drain | auth:sanctum (operator/admin/agronomist/engineer) | Режим слива зоны |
| POST | /api/zones/{id}/calibrate-flow | auth:sanctum (operator/admin/agronomist/engineer) | Калибровка датчика расхода |
| POST | /api/zones/{id}/calibrate-pump | auth:sanctum (operator/admin/agronomist/engineer) | Калибровка дозирующей помпы (ml/sec) |
| POST | /api/zones/{id}/grow-cycles | auth:sanctum (agronomist) | Создать новый grow cycle для зоны |
| GET | /api/zones/{id}/health | auth:sanctum | Состояние зоны + launch readiness для мастеров запуска |
| POST | /api/grow-cycles/{id}/pause | auth:sanctum (agronomist) | Пауза grow cycle |
| POST | /api/grow-cycles/{id}/resume | auth:sanctum (agronomist) | Возобновление grow cycle |
| POST | /api/grow-cycles/{id}/set-phase | auth:sanctum (agronomist) | Ручной переход фазы grow cycle |
| POST | /api/grow-cycles/{id}/advance-phase | auth:sanctum (agronomist) | Переход на следующую фазу grow cycle |
| POST | /api/zones/{id}/commands | auth:sanctum (operator/admin/agronomist/engineer) | Отправить команду зоне |
| GET | /api/zones/{id}/state | auth:sanctum | Текущее состояние workflow автоматики зоны (`state`, `active_processes`, `current_levels`, `timeline`, `irr_node_state`) |
| GET | /api/zones/{id}/control-mode | auth:sanctum | Текущий режим управления автоматикой (`auto|semi|manual`) и доступные ручные шаги |
| POST | /api/zones/{id}/control-mode | auth:sanctum (operator) | Переключить режим управления автоматикой (`auto|semi|manual`) |
| POST | /api/zones/{id}/manual-step | auth:sanctum (operator) | Запустить ручной этап 2-бакового workflow (`manual`: из active/idle, `semi`: только active workflow-фаза) |
| GET | /api/zones/{id}/telemetry/last | auth:sanctum | Последняя телеметрия |
| GET | /api/zones/{id}/telemetry/history| auth:sanctum | История телеметрии по метрикам |

Контракт `PATCH /api/zones/{id}`:
- допускает `automation_runtime: "ae3"`
- при busy zone возвращает `409` с `code=runtime_switch_denied_zone_busy`
- busy zone определяется через active `ae_tasks`, active `ae_zone_leases` или indeterminate `ae_commands` state

Контракт `POST /api/zones/{id}/calibrate-pump`:
- не блокируется по `zones.status`;
- требует, чтобы `node_channel_id` принадлежал выбранной зоне;
- физический прогон помпы (`skip_run=false`) валидируется по online-статусу конкретной ноды уже в `history-logger/common.water_flow`, а не по coarse-grained статусу зоны.
- `duration_sec` валидируется по `system.pump_calibration_policy`, а не по hardcoded controller-bound;
- первый шаг (`skip_run=false`, без `actual_ml`) возвращает `data.run_token` для двухшагового UX `run -> measure -> save`;
- второй шаг (`skip_run=true`, с `actual_ml`) требует `run_token`, если это сохранение после физического прогона; для явного manual persist без correlated run используется `manual_override=true`;
- mirror в `node_channels.config.pump_calibration` обновляется merge-патчем и не должен затирать соседние config-ключи канала.

Контракт `GET /api/zones/{id}/health`:
- содержит агрегированный `readiness` для запуска цикла;
- readiness fail-closed учитывает не только bind-ы/калибровки/PID, но и `automation_engine.grow_cycle_start_dispatch_enabled`;
- readiness включает `blocking_alerts` для hard-block кодов automation-engine (`biz_zone_correction_config_missing`, `biz_zone_dosing_calibration_missing`).

Контракт `GET /api/zones/{id}/state`:
- `active_processes.ph_correction` и `active_processes.ec_correction` для `automation_runtime='ae3'` отражают активный correction sub-machine (`corr_dose_*` / `corr_wait_*`), а не только top-level stage.
- поле `solution_tank_guard` (если присутствует) отражает последний non-blocking startup guard по solution tank: `checked`, `reset`, `reason`, `sensor_label`, `sample_ts`.
- если `zone_workflow_state` ссылается на уже terminal `ae_task` или отстаёт от `ae_tasks.updated_at`, endpoint обязан считать такой workflow snapshot stale и возвращать состояние по последней terminal task, а не показывать ложную active phase.

---

## 4. Nodes

| Метод | Путь | Auth | Описание |
|-------|----------------------|------|-----------------------------------------------|
| GET | /api/nodes | auth:sanctum | Список узлов |
| POST | /api/nodes | auth:sanctum (operator/admin/agronomist/engineer) | Зарегистрировать узел |
| GET | /api/nodes/{id} | auth:sanctum | Детали узла |
| PATCH | /api/nodes/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить метаданные узла (name, zone_id) |
| DELETE| /api/nodes/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить узел |

Доп. действия:

| Метод | Путь | Auth | Описание |
|-------|------------------------------------|------|--------------------------------------------------|
| GET | /api/nodes/{id}/telemetry/last | auth:sanctum | Последняя телеметрия по узлу |
| GET | /api/nodes/{id}/config | auth:sanctum | Получить сохраненный NodeConfig (read-only) |
| POST | /api/nodes/{id}/commands | auth:sanctum (operator/admin/agronomist/engineer) | Отправка низкоуровневых команд |
| PATCH | /api/node-channels/{id} | verify.python.service | Сервисное обновление `node_channels.config` (калибровки) |
| POST | /api/setup-wizard/validate-devices | auth:sanctum (operator/admin/agronomist/engineer) | Валидация zonal bindings внутри шага `4. Автоматика зоны` |
| POST | /api/setup-wizard/apply-device-bindings | auth:sanctum (operator/admin/agronomist/engineer) | Привязка zonal roles (`irrigation`, `ph/ec`, `light`, `zone_climate`) к каналам выбранных нод внутри блоков шага `4. Автоматика зоны` |
| POST | /api/setup-wizard/validate-greenhouse-climate-devices | auth:sanctum (operator/admin/agronomist/engineer) | Валидация greenhouse climate nodes для шага `1. Теплица` |
| POST | /api/setup-wizard/apply-greenhouse-climate-bindings | auth:sanctum (operator/admin/agronomist/engineer) | Привязка greenhouse roles (`climate_sensor`, `weather_station_sensor`, `vent_actuator`, `fan_actuator`) |

---

## 5. Recipes

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /api/recipes | auth:sanctum | Список рецептов |
| POST | /api/recipes | auth:sanctum (operator/admin/agronomist/engineer) | Создать рецепт |
| GET | /api/recipes/{id} | auth:sanctum | Детали рецепта |
| PATCH | /api/recipes/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить рецепт |
| DELETE| /api/recipes/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить рецепт |

### Ревизии рецептов (revisions-based)

| Метод | Путь | Auth | Описание |
|-------|-------------------------------|------|------------------------------------|
| POST | /api/recipes/{id}/revisions | auth:sanctum (agronomist) | Создать DRAFT-ревизию рецепта |
| PATCH | /api/recipe-revisions/{id} | auth:sanctum (agronomist) | Обновить DRAFT-ревизию |
| POST | /api/recipe-revisions/{id}/publish | auth:sanctum (agronomist) | Опубликовать DRAFT-ревизию |
| GET | /api/recipe-revisions/{id} | auth:sanctum | Получить ревизию рецепта |
| POST | /api/recipe-revisions/{id}/phases | auth:sanctum (operator/admin/agronomist/engineer) | Добавить фазу ревизии |
| PATCH | /api/recipe-revision-phases/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить фазу ревизии |
| DELETE| /api/recipe-revision-phases/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить фазу ревизии |

### Атомарное создание культуры и рецепта

| Метод | Путь | Auth | Описание |
|-------|-------------------------------|------|------------------------------------|
| POST | /api/plants/with-recipe | auth:sanctum (operator/admin/agronomist/engineer) | Атомарно создать `plant + recipe + draft revision + phases + publish` |

Канонический write-contract для phase payload в этом и обычных recipe endpoints:

- flat поля `recipe_revision_phases`;
- явные `ph_target/ph_min/ph_max` и `ec_target/ec_min/ec_max` обязательны для create phase;
- `target` валидируется относительно своего окна и должен лежать внутри `min..max`;
- `extensions.day_night`;
- `extensions.subsystems.irrigation.targets.system_type`.

Legacy `extensions.day_target/night_target` больше не используется.

---

## 6. Telemetry / History

| Метод | Путь | Auth | Описание |
|-------|----------------------------------------------|------|-----------------------------------------------|
| GET | /api/zones/{id}/telemetry/last | auth:sanctum | Последние значения по зоне |
| GET | /api/zones/{id}/telemetry/history | auth:sanctum | История по зоне |
| GET | /api/nodes/{id}/telemetry/last | auth:sanctum | Последние значения по узлу |

---

## 7. Alerts / Events

| Метод | Путь | Auth | Описание |
|-------|------------------------------|------|-----------------------------------|
| GET | /api/alerts | auth:sanctum | Список алертов |
| GET | /api/alerts/{id} | auth:sanctum | Детали алерта |
| PATCH | /api/alerts/{id}/ack | auth:sanctum (operator/admin/agronomist/engineer) | Подтвердить/принять алерт |
| GET | /api/alerts/stream | auth:sanctum | Server-Sent Events поток алертов |

---

## 8. Users (Admin only)

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /api/users | auth:sanctum (admin) | Список пользователей (фильтры: role, search) |
| POST | /api/users | auth:sanctum (admin) | Создать пользователя |
| GET | /api/users/{id} | auth:sanctum (admin) | Детали пользователя |
| PATCH | /api/users/{id} | auth:sanctum (admin) | Обновить пользователя (имя, email, пароль, роль) |
| DELETE| /api/users/{id} | auth:sanctum (admin) | Удалить пользователя |

---

## 8.1 User Preferences

| Метод | Путь | Auth | Описание |
|-------|--------------------------|------|-------------------------------------|
| GET | /settings/preferences | web auth | Получить пользовательские UI-настройки |
| PATCH | /settings/preferences | web auth | Обновить пользовательские UI-настройки |

Текущее поле:
- `alert_toast_suppression_sec` (0..600) — окно подавления повторных toast-уведомлений алертов.

---

## 9. System

| Метод | Путь | Auth | Описание |
|-------|---------------------------------|------|-------------------------------------------|
| GET | /api/system/config/full | verify.python.service (Sanctum или service token) | Экспорт полной конфигурации (для Python сервисов) |
| GET | /api/system/health | public | Проверка здоровья сервиса |
| GET | /api/system/scheduler/metrics | public | Prometheus exposition для Laravel scheduler (`dispatches`, `cycle_duration`, `active_tasks`); `counter`/`histogram` читаются из персистентных aggregate tables, а не из `scheduler_logs` |
| GET | /api/automation-configs/system/0/{namespace} | auth:sanctum (admin) | Получить system authority document |
| PUT | /api/automation-configs/system/0/{namespace} | auth:sanctum (admin) | Обновить system authority document |
| GET | /api/automation-configs/system/0/{namespace}/history | auth:sanctum (admin) | История версий system authority document |
| GET | /api/automation-bundles/system/0 | auth:sanctum (admin) | Получить compiled system bundle |
| POST | /api/automation-bundles/system/0/validate | auth:sanctum (admin) | Пересобрать и провалидировать system bundle |

Поддерживаемые system namespace:
- `system.runtime`
- `system.automation_defaults`
- `system.command_templates`
- `system.process_calibration_defaults`
- `system.pump_calibration_policy`
- `system.sensor_calibration_policy`

Authority-конфиги больше не публикуются в Inertia props для web-страниц.

---

## 10. Presets

| Метод | Путь | Auth | Описание |
|-------|------------------------------------------|------|-------------------------------------|
| GET | /api/automation-presets/{namespace} | auth:sanctum | Список preset-ов correction family по namespace |
| POST | /api/automation-presets/{namespace} | auth:sanctum (operator/admin/agronomist/engineer) | Создать custom preset |
| PUT/PATCH | /api/automation-presets/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Обновить custom preset |
| DELETE | /api/automation-presets/{id} | auth:sanctum (operator/admin/agronomist/engineer) | Удалить custom preset |
| POST | /api/automation-presets/{id}/duplicate | auth:sanctum (operator/admin/agronomist/engineer) | Дублировать preset в custom copy |

Preset rules:
- system preset read-only;
- custom preset editable;
- preset не является runtime authority, пока payload не сохранён в authority document.

---

## 11. Automation Authority API

| Метод | Путь | Auth | Описание |
|-------|---------------------------------------------------------------|------|-------------------------------------|
| GET | /api/automation-configs/{scopeType}/{scopeId}/{namespace} | auth:sanctum | Получить authority document |
| PUT | /api/automation-configs/{scopeType}/{scopeId}/{namespace} | auth:sanctum (scope-dependent role) | Обновить authority document |
| GET | /api/automation-configs/{scopeType}/{scopeId}/{namespace}/history | auth:sanctum | История версий authority document |
| GET | /api/automation-bundles/{scopeType}/{scopeId} | auth:sanctum | Получить compiled bundle |
| POST | /api/automation-bundles/{scopeType}/{scopeId}/validate | auth:sanctum (scope-dependent role) | Пересобрать и провалидировать bundle |

Поддерживаемые `scopeType`:

- `system`
- `zone`
- `grow_cycle`

Примеры namespace по scope:

- `system`: `system.runtime`, `system.automation_defaults`, `system.command_templates`
- `zone`: `zone.logic_profile`, `zone.correction`, `zone.pid.ph`, `zone.pid.ec`, `zone.process_calibration.*`
- `grow_cycle`: `cycle.start_snapshot`, `cycle.phase_overrides`, `cycle.manual_overrides`

Исключение:

- `greenhouse.logic_profile` читается и сохраняется через `/api/automation-configs/greenhouse/{id}/greenhouse.logic_profile`
- bundle endpoint для `greenhouse` не является частью текущего контракта

---

## 12. Reports & Analytics

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| GET | /api/recipes/{id}/analytics | auth:sanctum | Аналитика по рецепту |
| GET | /api/zones/{id}/harvests | auth:sanctum | История урожаев по зоне |
| POST | /api/harvests | auth:sanctum (operator/admin/agronomist/engineer) | Регистрация урожая |
| POST | /api/recipes/comparison | auth:sanctum | Сравнение рецептов |

---

## 13. AI

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/ai/predict | auth:sanctum | Прогнозирование параметров |
| POST | /api/ai/explain_zone | auth:sanctum | Объяснение состояния зоны |
| POST | /api/ai/recommend | auth:sanctum | Рекомендации AI |
| POST | /api/ai/diagnostics | auth:sanctum | Диагностика системы |

---

## 14. Simulations (Digital Twin)

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/simulations/zone/{zone} | auth:sanctum (operator/admin/agronomist/engineer) | Запуск симуляции |
| GET | /api/simulations/{job_id} | auth:sanctum | Статус симуляции + отчет |
| GET | /api/simulations/{simulation}/events | auth:sanctum | События процесса симуляции |
| GET | /api/simulations/{simulation}/events/stream | auth:sanctum | SSE-стрим событий симуляции |

---

## 15. Admin (минимальный CRUD)

| Метод | Путь | Auth | Описание |
|-------|----------------------------------------|------|-------------------------------------------|
| POST | /api/admin/zones/quick-create | auth:sanctum (admin) | Быстрое создание зоны |

---

## 15. Python integration

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/python/ingest/telemetry | token-based | Инжест телеметрии из Python‑сервисов |
| POST | /api/python/commands/ack | token-based | Подтверждение статусов команд (`SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED`) |

Примечание по `POST /api/python/commands/ack`:
- Терминальные статусы: `DONE`, `NO_EFFECT`, `ERROR`, `INVALID`, `BUSY`, `TIMEOUT`, `SEND_FAILED`.
- Переходы из terminal в non-terminal запрещены (anti-rollback guard).

---

## 16. Webhooks

| Метод | Путь | Auth | Описание |
|-------|-------------------------------------|------|-------------------------------------------|
| POST | /api/alerts/webhook | public | Webhook от Alertmanager для создания алертов |

---

## 17. Правила расширения REST API для ИИ-агентов

1. **Не менять семантику существующих путей и HTTP-методов.**
2. Для принципиально новых возможностей — добавлять новые пути
 (или версию `/api/v2/ ` при необходимости).
3. Любой новый публичный эндпоинт должен быть:
 - описан здесь;
 - интегрирован в `API_SPEC_FRONTEND_BACKEND_FULL.md`;
 - покрыт базовыми тестами.
4. Все действия, влияющие на физическое оборудование,
 должны проходить через Python-сервис, а не напрямую в MQTT.

Этот документ должен использоваться как **справочник** и основа для автодокументации (например, Swagger).

---

## 18. Internal Python Services (service-to-service)

### 18.1 Automation-engine health endpoints

| Метод | Путь | Auth | Описание |
|-------|----------------------|------|----------------------------------------------|
| GET | /health/live | internal | Liveness: процесс API доступен |
| GET | /health/ready | internal | Readiness: `CommandBus`, DB и bootstrap lease-store готовы |

### 18.2 Automation-engine runtime endpoints

| Метод | Путь | Auth | Описание |
|-------|-------------------------------|------|----------------------------------------------------|
| POST | /zones/{id}/start-cycle | internal | Единственный внешний wake-up зоны (scheduler/manual trigger) |
| GET | /zones/{id}/state | internal | Полный runtime-state зоны для UI/интеграций |
| GET | /zones/{id}/control-mode | internal | Текущий `control_mode`, `current_stage`, `pending_manual_step` и public manual-step список |
| POST | /zones/{id}/control-mode | internal | Переключение режима (`auto|semi|manual`) |
| POST | /zones/{id}/manual-step | internal | Запрос public manual-step для active canonical AE3 task |
| POST | /zones/{id}/start-relay-autotune | internal | Запуск relay-autotune PID (`pid_type: ph|ec`) для активной зоны |

Инварианты manual-control runtime path:
- `GET /zones/{id}/control-mode` всегда возвращает только public/generic manual-step коды:
  `clean_fill_start`, `solution_fill_start`, `clean_fill_stop`, `solution_fill_stop`, `prepare_recirculation_stop`;
- `semi` паузит `startup` перед входом в следующую fill-фазу, пока оператор не отправит соответствующий `manual-step`;
- `manual` паузит `startup` и check-стадии two-tank workflow, пока оператор не отправит соответствующий `manual-step`;
- `POST /zones/{id}/manual-step` принимает только canonical active task и возвращает canonical numeric `task_id`
  (в JSON строкой для совместимости внешнего контракта);
- при переключении в `auto` active `pending_manual_step` сбрасывается fail-closed.

Инварианты `POST /zones/{id}/start-cycle`:
- endpoint не несет device-level payload (минимальный wake-up контракт);
- endpoint принимает только `source` и `idempotency_key`;
- фактические действия определяются pending intent-ами в БД;
- повторный вызов с тем же `idempotency_key` не должен создавать дублирующее выполнение;
- при активном intent этой же зоны (другой `idempotency_key`) endpoint возвращает `409 start_cycle_zone_busy`;
- при активной scheduler-задаче зоны (`accepted|running`) endpoint возвращает `409 start_cycle_zone_busy`
  с `active_task_id` и `active_task_status`;
- при блокирующей `workflow_phase` без активной scheduler-задачи endpoint выполняет auto-heal/reset в `idle`,
  если возраст фазы превышает `AE_START_CYCLE_ORPHAN_PHASE_AUTO_HEAL_SEC` (по умолчанию 600 сек);
- если зона была в `ready`, но сработал `solution_min` датчик бака раствора, AE3 перед
  обработкой wake-up сбрасывает `zone_workflow_state` в `idle` с
  `payload.ae3_cycle_start_stage='startup'`, чтобы зона перестала считаться готовой к поливу
  и следующий `cycle_start` шёл через refill/startup path;
- если execution самого `solution_tank` startup guard завершился инфраструктурной ошибкой,
  endpoint fail-closed отвечает `503 start_cycle_solution_tank_guard_failed`
  и не claim-ит новый intent/task;
- при terminal intent endpoint возвращает `accepted=false`, `runner_state=terminal`,
  `task_status` и `reason=start_cycle_intent_terminal`.
- для зон с `zones.automation_runtime='ae3'` поле `task_id` содержит canonical numeric AE3 task id
  (в JSON остаётся строкой для совместимости внешнего контракта);
- если AE3-ответ не содержит canonical numeric `task_id`, Laravel scheduler трактует submit как failed/retryable
  и не создаёт fallback snapshot с `intent-*`;
- legacy `intent-*` task snapshots удалены; runtime обязан возвращать canonical numeric `task_id`.

Контракт `POST /zones/{id}/start-relay-autotune`:
- тело запроса: `{ "pid_type": "ph" | "ec" }`;
- endpoint требует активную фазу workflow зоны (не `idle`), иначе `409 relay_autotune_zone_inactive`;
- при уже запущенном autotune для зоны/типа возвращает `409 relay_autotune_already_running`.

Минимальный request:
```json
{
  "source": "laravel_scheduler",
  "idempotency_key": "sch:z12:irrigation:2026-02-21T10:00:00Z"
}
```

Response:
```json
{
  "status": "ok",
  "data": {
    "zone_id": 12,
    "accepted": true,
    "runner_state": "active",
    "deduplicated": false,
    "task_id": "321",
    "idempotency_key": "sch:z12:irrigation:2026-02-21T10:00:00Z"
  }
}
```

Response (terminal intent):
```json
{
  "status": "ok",
  "data": {
    "zone_id": 12,
    "accepted": false,
    "runner_state": "terminal",
    "deduplicated": true,
    "task_id": "321",
    "idempotency_key": "sch:z12:irrigation:2026-02-21T10:00:00Z",
    "task_status": "failed",
    "reason": "start_cycle_intent_terminal"
  }
}
```

Response (zone busy, active intent):
```json
{
  "detail": {
    "error": "start_cycle_zone_busy",
    "zone_id": 12,
    "active_intent_id": 889,
    "active_status": "running"
  }
}
```

Response (zone busy, active task):
```json
{
  "detail": {
    "error": "start_cycle_zone_busy",
    "zone_id": 12,
    "active_task_id": "st-running",
    "active_task_status": "running"
  }
}
```

Response (solution tank guard failed):
```json
{
  "detail": {
    "error": "start_cycle_solution_tank_guard_failed",
    "zone_id": 12,
    "message": "solution tank startup guard failed"
  }
}
```

### 18.3 Scheduler intents lifecycle (DB contract)

`POST /zones/{id}/start-cycle` работает только как wake-up endpoint.
Фактическое выполнение берется из `zone_automation_intents`.

Lifecycle intents:
- `pending`
- `claimed`
- `running`
- `completed`
- `failed`
- `cancelled`

Правила:
- scheduler сначала пишет intent (`pending`) в БД, затем вызывает `start-cycle`;
- `automation-engine` claim-ит intent через row lock (`FOR UPDATE SKIP LOCKED`);
- при повторном `idempotency_key` для active intent endpoint возвращает
  `accepted=true` + `deduplicated=true` без повторного выполнения device-команд;
- если после claim обнаружена активная scheduler-задача зоны, intent переводится обратно в `pending`,
  а endpoint возвращает `409 start_cycle_zone_busy`;
- если обнаружена orphan/stuck `workflow_phase` без активной scheduler-задачи и возраст фазы выше
  `AE_START_CYCLE_ORPHAN_PHASE_AUTO_HEAL_SEC`, runtime сбрасывает `zone_workflow_state.workflow_phase` в `idle`
  и продолжает старт цикла;
- при повторном `idempotency_key` для terminal intent endpoint возвращает
  `accepted=false` + `runner_state=terminal` + `task_status`;
- stale `claimed` intent может быть re-claimed после таймаута
  `AE_START_CYCLE_CLAIM_STALE_SEC` (по умолчанию 180 сек) c инкрементом `retry_count`.

`zone_automation_intents.payload` (wake-up only):
```json
{
  "source": "laravel_scheduler",
  "task_type": "diagnostics",
  "workflow": "cycle_start",
  "topology": "two_tank_drip_substrate_trays",
  "grow_cycle_id": 123
}
```

Ограничения payload:
- `task_payload` и `schedule_payload` запрещены;
- любые device-level steps/commands запрещены;
- при наличии legacy-ключей runtime трактует их как невалидные для контракта wake-up only.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

### 18.4 PID Advanced (Laravel API)

Новые публичные endpoint-ы для панели PID/калибровок (frontend):

| Метод | Путь | Auth | Описание |
|-------|---------------------------------------------|------|-------------------------------------------|
| GET | /api/zones/{zone}/pump-calibrations | auth:sanctum (viewer+) | Список дозирующих насосов зоны с активной калибровкой |
| PUT | /api/zones/{zone}/pump-calibrations/{channelId} | auth:sanctum (operator+) | Сохранить новую калибровку `ml_per_sec` (создаёт новую запись в `pump_calibrations`) |
| GET | /api/zones/{zone}/sensor-calibrations | auth:sanctum | История calibration sessions по pH/EC сенсорам зоны |
| GET | /api/zones/{zone}/sensor-calibrations/status | auth:sanctum | Статус по каждому sensor channel: `ok|warning|critical|never` и наличие active session |
| GET | /api/zones/{zone}/sensor-calibrations/{id} | auth:sanctum | Детали одной calibration session |
| POST | /api/zones/{zone}/sensor-calibrations | auth:sanctum (operator+) | Создать calibration session для `node_channel_id` и `sensor_type=ph|ec` |
| POST | /api/zones/{zone}/sensor-calibrations/{id}/point | auth:sanctum (operator+) | Отправить stage 1 или stage 2 через `history-logger POST /commands` |
| POST | /api/zones/{zone}/sensor-calibrations/{id}/cancel | auth:sanctum (operator+) | Отменить не-terminal calibration session |
| POST | /api/zones/{zone}/relay-autotune | auth:sanctum (operator+) | Запуск relay-autotune через proxy в automation-engine |
| GET | /api/zones/{zone}/relay-autotune/status | auth:sanctum (viewer+) | Статус relay-autotune через proxy в automation-engine |

Контракт `PUT /api/zones/{zone}/pump-calibrations/{channelId}`:
- request body: `{ "ml_per_sec": number, "k_ms_per_ml_l"?: number }`;
- min/max validation и default duration берутся из `system.pump_calibration_policy`;
- деактивирует предыдущую активную калибровку `node_channel_id`;
- создаёт `zone_event` типа `PUMP_CALIBRATION_SAVED`.

Контракт `GET/PUT /api/automation-configs/zone/{zone}/zone.correction`:
- `payload.resolved_config.pump_calibration` обязателен для correction runtime;
- `payload.base_config.pump_calibration` хранит только zone-level override diff;
- история документа доступна через `GET /api/automation-configs/zone/{zone}/zone.correction/history`.

Контракт `POST /api/zones/{zone}/sensor-calibrations/{id}/point`:
- request body: `{ "stage": 1|2, "reference_value": number }`;
- `reference_value` валидируется против `system.sensor_calibration_policy`;
- `stage=1` допустим только из `started`;
- `stage=2` допустим только из `point_1_done`;
- publish calibration command запрещён для offline-ноды и возвращает `422`, не переводя сессию в pending по timeout-path;
- успешный enqueue переводит session в `point_1_pending` или `point_2_pending`;
- terminal status `DONE` приходит через `POST /api/python/commands/ack` и переводит session в `point_1_done` либо оставляет stage 2 в `point_2_pending` с `meta.awaiting_config_report=true`;
- финальный переход в `completed` для stage 2 происходит только после `config_report` от ноды с persisted calibration namespace (`NodeConfig.calibration`);
- terminal status `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` переводит session в `failed`.

Контракт `POST /api/zones/{zone}/relay-autotune`:
- request body: `{ "pid_type": "ph" | "ec" }`;
- требует активный grow cycle зоны;
- создаёт `zone_event` типа `RELAY_AUTOTUNE_STARTED`;
- проксирует запрос в automation-engine endpoint `/zones/{id}/start-relay-autotune`.
