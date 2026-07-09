# ERROR_CODE_CATALOG.md
# Канонический каталог кодов ошибок automation/runtime

**Версия:** 1.5
**Дата:** 2026-06-29
**Статус:** Актуально (фаза 5: прошивки/MQTT command_response; фаза 4: UI fallback)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Зафиксировать канонический contract для ошибок automation/runtime:

- backend и AE3 передают наружу `error_code`;
- frontend показывает локализованное описание по коду;
- raw `error_message` считается debug-context и запасным каналом без строгого контракта, но не business contract.

Полный машиночитаемый source of truth:

- `backend/error_codes.json` — backend + AE3 + UI (включая слияние кодов узлов)
- `backend/node_error_codes.json` — только `error_code` из `command_response` ESP32 / MQTT (фаза 5)

Производные копии для Laravel/frontend runtime:

- `backend/laravel/error_codes.json`
- `backend/laravel/resources/js/constants/error_codes.json`

## Правила

1. Все новые ошибки automation-engine обязаны иметь стабильный `error_code`.
2. Английский raw-text не может использоваться как ключ ветвления в runtime logic.
3. Если код отсутствует в каталоге, это считается регрессией.
4. Для исторических записей без кода допускается только compatibility fallback локализации.
5. Публичные JSON-ответы об ошибке **обязаны** содержать `human_error_message` (см. контракт ниже).

## Контракт REST API (фаза 2)

### Каноническое тело ошибки

Все ошибки Laravel API и прокси AE3 возвращают (минимум):

```json
{
  "status": "error",
  "code": "snake_case_code",
  "message": "Текст на русском для оператора",
  "human_error_message": "Тот же текст, что message (дублируется для UI)",
  "title": "Краткий заголовок из каталога"
}
```

Дополнительные поля (`errors`, `details`, `correlation_id`, `data`) сохраняются без изменения семантики.

### Нормализация кода

- В JSON всегда **lowercase `snake_case`** (`cycle_already_active`, не `CYCLE_ALREADY_ACTIVE`).
- Источник перевода: `backend/error_codes.json` через `ErrorCodeCatalogService` (Laravel) и `common/error_catalog.py` (Python).
- Если в каталоге нет записи, но upstream передал текст — **оставляем исходный `message` как есть** (фаза 4).
- Если есть только `code` без текста — русский fallback `Внутренняя ошибка системы (код: …)`.

### Слои реализации

| Слой | Компонент | Назначение |
| --- | --- | --- |
| Laravel | `ErrorCodeCatalogService` | `errorPayload()`, `enrichErrorPayload()` |
| Laravel | `PresentsLocalizedApiErrors` (trait контроллеров) | `localizedError()`, `buildAutomationEngineErrorResponse()` |
| Laravel | `LocalizedApiJsonResponse` | глобальный handler в `bootstrap/app.php` |
| AE3 | `present_error()`, `enrich_error_payload()` | ingress и HTTPException handler |
| Frontend | `resolveHumanErrorMessage()` | приоритет: `human_error_message` → каталог → raw map → исходный `message` |

### Прокси automation-engine

При 4xx от AE3 Laravel вызывает `enrichErrorPayload()` на теле ответа (в т.ч. вложенный FastAPI `detail`), чтобы UI получил русский `human_error_message` без дублирования логики во Vue.

### Проверка в CI

```bash
make i18n-catalog-check
python3 backend/scripts/audit_phase2_api_i18n.py
python3 backend/scripts/audit_phase5_firmware_i18n.py
```

## Фаза 5: прошивки и MQTT `command_response`

Коды `error_code` в ответах узлов (`status=ERROR|INVALID|BUSY`) локализуются тем же lookup, что и backend-коды, после слияния в `error_codes.json`.

| Артефакт | Назначение |
| --- | --- |
| `backend/scripts/firmware_error_codes.py` | Manifest + извлечение из `firmware/`, MQTT-доков, `tests/node_sim` |
| `backend/scripts/build_node_error_catalog.py` | Сборка `node_error_codes.json` и merge в `error_codes.json` |
| `backend/node_error_codes.json` | Канон каталога слоя узлов (`layer=firmware_mqtt`) |
| `backend/scripts/audit_phase5_firmware_i18n.py` | CI: полнота извлечения, кириллица, MQTT spec |

Обновление каталога:

```bash
python3 backend/scripts/build_node_error_catalog.py
python3 backend/scripts/sync_i18n_catalogs.py
```

Политика:

1. Новый `error_code` в прошивке → запись в `FIRMWARE_ERROR_MANIFEST` с русским `message`.
2. `make i18n-catalog-check` падает, если код есть в firmware/MQTT, но отсутствует в `node_error_codes.json`.
3. UI/command toast: `code` / `error_code` → `resolveHumanErrorMessage()` / `ErrorCodeCatalogService::present()`.
4. Префикс `esp_` (диагностика ESP-IDF) — lookup по полному коду или шаблону `esp_*` в каталоге.

## Android (фаза 3)

Копии каталогов в assets (синхронизируются скриптом `backend/scripts/sync_i18n_catalogs.py`):

- `mobile/app/android/app/src/main/assets/i18n/error_codes.json`
- `mobile/app/android/app/src/main/assets/i18n/alert_codes.json`

Runtime:

- `ErrorCatalog` / `AlertCatalog` — lookup по `code`;
- `ApiErrorParser` — разбор HTTP-ошибок Laravel (`human_error_message`, `code`, `message`);
- приоритет отображения совпадает с Vue: `human_error_message` → каталог → исходный `message` (фаза 4).

Unit-тесты: `mobile/app/android/app/src/test/java/com/hydro/app/core/i18n/ErrorCatalogTest.kt`.

## Frontend / UI (фаза 4)

Политика `resolveHumanErrorMessage()` (Vue) и `extractHumanErrorMessage()`:

1. `human_error_message` / `humanMessage` от API;
2. уже русский `message`;
3. известные шаблоны (INA209, Axios HTTP status);
4. запись в `error_codes.json` по `code`;
5. `RAW_MESSAGE_TRANSLATIONS` / regex для legacy English;
6. **исходный `message` без изменений**, если перевода нет;
7. только `code` без текста → `Внутренняя ошибка системы (код: …)`.

Интеграция: `useErrorHandler`, `errorMessage.ts`, `alertMeta.ts`, `useAlertsPage`, WebSocket command toast, `eventPayload.humanizeEventError`.

Алерты без записи в `alert_codes.json`: описание берётся из `details.message` или Prometheus `annotations.description` / `summary` (через `AlertMessageComposer` и `AlertCatalogService`), иначе нейтральный русский fallback.

### 100% покрытие API (2026-06-03)

- `LocalizeApiErrorResponse` middleware — все JSON `status=error` на `/api/*` обогащаются `human_error_message`.
- `backend/api_error_raw_translations.json` — точные переводы inline English из CRUD-контроллеров (синхронизируется в `laravel/`, `services/common/`).
- `PresentsLocalizedApiErrors` на базовом `Controller`.
- Prometheus `MQTTBrokerDown` → код каталога `mqtt_broker_down`.
- history-logger: `HTTPException` handler через `common/fastapi_http_errors.py`.

Проверка:

```bash
make i18n-catalog-check   # включает audit_phase4_i18n_coverage.py
```

## Таблица кодов Laravel API (`NodeController` / привязка узлов)

| code | HTTP | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `zone_automation_binding_conflict` | 422 | UI-привязка узла к зоне: в зоне уже есть другой узел с тем же критичным датчиком (pH/EC) или та же роль полива/коррекции занята в `channel_bindings` | Текст из `message` ответа API (детальное объяснение + uid узла); fallback в `error_codes.json`. |
| `node_operation_rejected` | 422 | Прочие `DomainException` из `NodeService::update` (например, недопустимый lifecycle при привязке) | Текст из `message` ответа API; fallback в `error_codes.json`. |

## Таблица кодов AE3 snapshot/runtime

| code | Домен | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `ae3_snapshot_build_failed` | `ae3_snapshot` | Общая ошибка сборки runtime-снимка без более точной классификации | `AE3 не смог собрать консистентный runtime-снимок зоны для запуска автоматического цикла.` |
| `ae3_snapshot_zone_not_found` | `ae3_snapshot` | Зона не найдена в read-model | `AE3 не нашёл зону, для которой должен был собрать runtime-снимок.` |
| `ae3_snapshot_no_active_grow_cycle` | `ae3_snapshot` | У зоны нет активного цикла выращивания | `Для зоны не найден активный цикл выращивания, поэтому автоматический запуск невозможен.` |
| `ae3_snapshot_missing_current_phase` | `ae3_snapshot` | У активного цикла не задана текущая фаза | `У активного цикла выращивания не задана текущая фаза, поэтому AE3 не может построить runtime-снимок.` |
| `ae3_snapshot_bundle_missing` | `ae3_snapshot` | Для grow cycle отсутствует compiled bundle | `Для активного цикла отсутствует compiled automation bundle, необходимый для работы AE3.` |
| `ae3_snapshot_bundle_invalid` | `ae3_snapshot` | Bundle существует, но имеет некорректный формат | `Compiled automation bundle имеет некорректный формат и не может быть использован AE3.` |
| `ae3_snapshot_zone_bundle_missing` | `ae3_snapshot` | В bundle нет секции `zone` | `В compiled automation bundle отсутствует конфигурация зоны, обязательная для AE3.` |
| `ae3_snapshot_logic_profile_bundle_missing` | `ae3_snapshot` | В zone bundle нет `logic_profile` | `В конфигурации зоны отсутствует активный logic profile bundle, необходимый для runtime.` |
| `ae3_snapshot_active_logic_profile_missing` | `ae3_snapshot` | Не выбран активный automation profile | `Для зоны не выбран активный automation logic profile, поэтому запуск AE3 запрещён.` |
| `ae3_snapshot_empty_command_plans` | `ae3_snapshot` | В активном профиле нет `command_plans` | `В активном automation profile отсутствуют command plans для выполнения цикла.` |
| `ae3_snapshot_no_online_actuator_channels` | `ae3_snapshot` | В зоне нет ни одного online actuator/service channel. SQL-фильтр учитывает `nodes.status='online'` либо свежий `last_seen_at` в окне `AE3_NODE_FRESHNESS_FALLBACK_SEC`. В payload `details` приходит per-node breakdown (`zone_nodes`, `persistently_offline_uids`, `transiently_offline_uids`, `persistent_dead_threshold_sec`). | `В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.` |
| `ae3_snapshot_required_node_persistently_offline` | `ae3_snapshot` | Один или несколько узлов зоны не подают признаков жизни ≥ `AE3_NODE_PERSISTENT_DEAD_SEC` (default 600). AE3 не выполняет retry, чтобы не зависать. Конкретные `node_uid` приходят в `details.persistently_offline_uids`. | `Один или несколько узлов зоны давно не выходят на связь. AE3 завершил задачу без повторов — проверьте питание и сеть нод.` |
| `ae3_snapshot_required_node_type_missing` | `ae3_snapshot` | Для текущей топологии (`two_tank` / `two_tank_drip_substrate_trays`) в зоне отсутствует actuator хотя бы для одного из обязательных `node_type` (`irrig`, `ph`, `ec`). В `details.missing_node_types` — список недостающих типов. | `Для двухбакового цикла в зоне нет нод обязательных типов (irrig/ph/ec). Проверьте регистрацию узлов.` |
| `ae3_snapshot_conflicting_config_values` | `ae3_snapshot` | Merge runtime-конфига выявил противоречие | `AE3 обнаружил конфликтующие значения в runtime-конфигурации и остановил запуск fail-closed.` |
| `ae3_snapshot_retry_exhausted` | `ae3_snapshot` | Retry на transient snapshot gap исчерпан (бюджет = `AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC`, default 600). В `details` дополнительно приходят `zone_nodes`, `persistently_offline_uids`, `transiently_offline_uids` для расследования. | `AE3 не смог восстановить transient snapshot gap за допустимое время и завершил задачу с ошибкой.` |
| `ae3_snapshot_retry_persist_failed` | `ae3_snapshot` | Не удалось сохранить повтор retry после transient gap | `AE3 не смог сохранить задачу для повторной попытки после transient snapshot gap.` |
| `unsupported_command_plan_steps` | `ae3_execution` | Planner выдал некорректный набор шагов | `AE3 получил command plan без обязательных шагов и остановил выполнение.` |
| `command_timeout` | `command` | Не пришёл terminal status команды | `Не дождались подтверждения или итогового ответа по команде в допустимое время.` |
| `command_send_failed` | `command` | Не удалось передать команду в transport path | `Команду не удалось отправить до исполнительного узла.` |
| `ae3_task_execution_crashed` | `ae3_execution` | Worker поймал необработанное исключение в `_execute_claimed_task` и изолировал сбой per-task | `Выполнение задачи AE3 аварийно прервано runtime worker; задача переведена в failed.` |
| `ae3_task_execution_timeout` | `ae3_execution` | Вся задача превысила runtime timeout | `Выполнение задачи AE3 превысило допустимый runtime timeout.` |
| `ae3_task_execution_unhandled_exception` | `ae3_execution` | Во время выполнения произошло необработанное исключение | `Во время выполнения задачи AE3 произошло необработанное исключение.` |
| `start_irrigation_setup_pending` | `ae3_ingress` | `POST /zones/{id}/start-irrigation` вызван до перехода зоны в `workflow_phase='ready'` (или `zone_workflow_state` ещё не создан) | `Полив отклонён: зона ещё не готова. Сначала завершите setup/cycle_start.` |
| `irr_state_unavailable` | `ae3_irr_probe` | Probe IRR-ноды не получил snapshot за `irr_state_wait_timeout_sec` (нода offline / mqtt disconnect / reboot). В polling-стейджах поглощается backoff'ом, эскалируется только при достижении `_IRR_PROBE_FAILURE_STREAK_LIMIT` | `Снимок состояния IRR-ноды недоступен.` |
| `irr_state_stale` | `ae3_irr_probe` | Snapshot получен, но `age > irr_state_max_age_sec`. Семантика как у `irr_state_unavailable` (deferred в polling-стейджах) | `Снимок состояния IRR-ноды устарел.` |
| `irr_state_mismatch` | `ae3_irr_probe` | Snapshot пришёл, но hardware state не совпал с `expected` (valve/pump). **Не** оборачивается backoff'ом — это safety boundary, fail-closed немедленно | `Состояние IRR-ноды не совпало с ожиданиями автоматики.` |
| `irrigation_recovery_probe_exhausted` | `ae3_irr_probe` | В `irrigation_recovery_check` исчерпан streak подряд идущих deferred probes (`_IRR_PROBE_FAILURE_STREAK_LIMIT=5`) — нода долго недоступна | `IRR-нода недоступна: исчерпан лимит подряд идущих probe-deferrals.` |
| `ae3_prepare_recirculation_max_attempts_missing` | `ae3_config` | В bundle коррекции для prepare-recirculation отсутствует обязательный `prepare_recirculation_max_attempts` (Phase 3.1 B-7 fail-closed) | `В конфигурации коррекции отсутствует обязательный параметр числа повторов prepare-recirculation.` |

## Таблица кодов AE3 ingress / task creation

| code | Домен | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `start_cycle_zone_busy` | `ae3_ingress` | `POST /zones/{id}/start-cycle` / `start-irrigation` / `start-lighting-tick` при наличии active task или active lease | `Зона занята другим запуском, повторите попытку после завершения текущей задачи.` |
| `start_cycle_idempotency_key_conflict` | `ae3_ingress` | Тот же `(zone_id, idempotency_key)` уже использован другим intent | `Идентичный запуск уже зарегистрирован, дублирующий запрос отклонён.` |
| `start_cycle_missing_idempotency_key` | `ae3_ingress` | Запрос на ingress без `idempotency_key` | `В запросе отсутствует ключ идемпотентности — повторите с уникальным идентификатором.` |
| `start_cycle_unsupported_runtime` | `ae3_ingress` | Зона не на AE3 runtime, но получен start-cycle/start-irrigation | `Start-cycle доступен только для зон на AE3 runtime.` |
| `start_cycle_solution_tank_guard_failed` | `ae3_ingress` | Startup guard бака раствора завершился ошибкой до claim intent | `Не пройдена startup-проверка бака раствора перед start-cycle.` |
| `start_irrigation_intent_not_found` | `ae3_ingress` | Intent для start-irrigation не найден | `Intent для start-irrigation не найден.` |
| `start_lighting_tick_intent_not_found` | `ae3_ingress` | Intent для start-lighting-tick не найден | `Intent для start-lighting-tick не найден.` |
| `start_lighting_tick_zone_busy` | `ae3_ingress` | Зона занята при start-lighting-tick | `Запуск lighting tick отклонён: зона уже занята активной задачей.` |
| `unauthorized` | `ae3_security` | Неверный или отсутствующий Bearer token на ingress AE3 | `Запрос отклонён: неверный или отсутствующий Bearer token.` |
| `missing_trace_id` | `ae3_security` | Отсутствует обязательный X-Trace-Id при enforce | `В запросе отсутствует обязательный заголовок X-Trace-Id.` |
| `scheduler_security_token_not_configured` | `ae3_security` | Scheduler API token не настроен на AE3 | `Automation-engine отклонил запрос: scheduler API token не сконфигурирован.` |
| `task_not_found` | `ae3_ingress` | Internal task status для несуществующей задачи | `Задача automation-engine не найдена.` |
| `ae3_internal_error` | `ae3_api` | Необработанное исключение в HTTP route AE3 | `Внутренняя ошибка automation-engine. Повторите позже или обратитесь к инженеру.` |
| `ae3_task_create_failed` | `ae3_ingress` | Не удалось вставить task в `ae_tasks` (DB-ошибка или нарушение constraints) | `AE3 не смог зарегистрировать задачу автоматики — попробуйте позже.` |
| `start_lighting_tick_unsupported_runtime` | `ae3_ingress` | Зона не на AE3 runtime, но получен `start-lighting-tick` | `Освещение по AE3 расписанию доступно только для зон на AE3 runtime.` |

## Таблица кодов AE3 execution / FSM

| code | Домен | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `ae3_complete_transition_failed` | `ae3_execution` | CAS-промах при переводе task в `completed` | `Не удалось финализировать задачу AE3 (несовместимая ревизия состояния).` |
| `ae3_transition_apply_failed` | `ae3_execution` | `WorkflowRouter` не смог применить `StageOutcome.transition` через `update_stage` | `Не удалось зафиксировать переход между этапами автоматики.` |
| `ae3_poll_apply_failed` | `ae3_execution` | Аналогично, для `StageOutcome.poll` | `Не удалось зарегистрировать повторный опрос этапа автоматики.` |
| `ae3_correction_apply_failed` | `ae3_execution` | Аналогично, для `StageOutcome.enter_correction` | `Не удалось войти в окно коррекции.` |
| `ae3_task_running_transition_failed` | `ae3_execution` | Не удалось перевести claimed→running | `Не удалось активировать задачу AE3 для выполнения.` |
| `ae3_required_node_offline` | `ae3_execution` | Обязательный узел зоны offline (transient) | `Узел зоны недоступен (offline): {uid} ({type}).` |
| `ae3_zone_lease_lost` | `ae3_execution` | Lease зоны потеряна mid-run | `Эксклюзивная блокировка зоны была потеряна, задача прервана.` |
| `ae3_zone_lease_release_failed` | `ae3_execution` | Не удалось отпустить lease после завершения | `Не удалось освободить блокировку зоны после задачи (требуется ручная проверка).` |
| `runtime_plan_missing` | `ae3_execution` | У task в `running/waiting_command` нет RuntimePlan | `Отсутствует runtime-план для активной задачи — задача отменена.` |
| `control_mode_switched_to_manual` | `ae3_execution` | Active task отменена переключением `control_mode='manual'` | `Задача отменена: оператор переключил зону в ручной режим.` |
| `ae3_command_send_retry_scheduled` | `ae3_execution` | Запланирован transient retry публикации команды | `Команда отправляется повторно из-за временного сбоя.` |
| `infra_ae3_snapshot_retry_scheduled` | `ae3_execution` | Transient snapshot gap, запланирован retry | `AE3 повторит попытку собрать снимок зоны.` |

## Таблица кодов startup recovery

Возвращаются `StartupRecoveryUseCase` для in-flight задач после рестарта AE3:

| code | Когда возникает |
| --- | --- |
| `startup_recovery_unconfirmed_command` | Task в `claimed/running` без подтверждённой внешней команды — переводится в `failed`. |
| `startup_recovery_pending_resume_failed` | Не удалось вернуть task из `waiting_command` обратно в `running`. |
| `startup_recovery_lease_release_failed` | Не удалось освободить просроченную lease. |
| `startup_recovery_orphan_lease_released` | Освобождена осиротевшая lease (information level). |
| `ae3_stale_task_reclaimed` | Task застряла в `claimed`/`running` дольше TTL — janitor перевёл в `failed` (или `requeue` без команд). |
| `ae3_flow_stop_unconfirmed` | Stop-команда flow-path завершилась без подтверждённого OFF (probe mismatch / timeout). |
| `ae3_manual_hold_deadline_exceeded` | `manual_hold` превысил сохранённый stage deadline. |
| `ae3_manual_hold_return_stage_missing` | `manual_hold` без `__mh_return:*` в `pending_manual_step`. |

## Таблица кодов irrigation / two-tank stage terminal

Stage-terminal коды используются `WorkflowRouter._fail_task` для безопасного завершения задачи внутри two-tank workflow:

| code | Стадия | Что значит |
| --- | --- | --- |
| `clean_tank_not_filled_timeout` | `clean_fill_check` | Чистый бак не наполнился за `clean_fill_timeout_sec`. |
| `clean_fill_source_empty_stop` | `clean_fill_*` | Источник воды пуст после исчерпания `1 + clean_fill_retry_cycles` (AE3 timeout/retry; production-нода обычно не шлёт `clean_fill_source_empty`). |
| `solution_fill_leak_detected` | `solution_fill_check` | Зафиксирована утечка раствора. |
| `solution_fill_leak_stop` | `solution_fill_*` | Stage остановлен из-за утечки. |
| `solution_fill_source_empty_stop` | `solution_fill_*` | Источник раствора пуст. |
| `solution_fill_timeout_stop` | `solution_fill_check` | Stage timeout / fail-closed по `no-effect`. |
| `prepare_recirculation_solution_low_stop` | `prepare_recirc_*` | Уровень раствора ниже минимального. |
| `prepare_recirculation_attempt_limit_reached` | `prepare_recirc_*` | Исчерпан `prepare_recirculation_max_attempts`. |
| `irrigation_decision_strategy_unknown` | `decision_gate` | Неизвестная irrigation strategy в конфиге. |

## Таблица кодов solution_change (черновик, этап D.1)

> **Статус:** doc-first; коды фиксируются при реализации runtime. Семантика — `CORRECTION_CYCLE_SPEC.md` §10.7, `ae3lite.md` §7.2.3.

| code | Домен | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `start_solution_change_zone_busy` | `ae3_ingress` | Active task/lease при `POST /zones/{id}/start-solution-change` | `Зона занята — подмену раствора нельзя начать сейчас.` |
| `solution_change_zone_not_ready` | `ae3_ingress` | `workflow_phase != ready` | `Подмена раствора доступна только когда зона в фазе «готова».` |
| `solution_change_active_irrigation` | `ae3_ingress` | Активный полив | `Дождитесь завершения полива перед подменой раствора.` |
| `solution_change_disabled` | `ae3_config` | `subsystems.solution_change.enabled=false` | `Подмена раствора отключена в настройках зоны/рецепта.` |
| `solution_change_topology_unsupported` | `ae3_config` | Не two-tank / нет IRR | `Контур зоны не поддерживает автоматическую подмену раствора.` |
| `solution_drain_timeout_stop` | `solution_drain_check` | Слив не завершён за `solution_drain_timeout_sec` | `Слив раствора не завершился в отведённое время.` |
| `solution_drain_incomplete_stop` | `solution_drain_check` | Уровень не подтверждён empty после drain | `Бак раствора не опустошён — подмена остановлена.` |
| `solution_change_operator_timeout` | `await_operator_*` | Истёк `solution_change_operator_confirm_timeout_sec` на gate | `Ожидание подтверждения оператора превысило лимит — задача остановлена.` |
| `solution_change_aborted_by_operator` | `solution_change` | Manual step `solution_change_abort` | `Подмена раствора отменена оператором.` |
| `solution_change_gate_invalid_step` | `ae3_manual` | Неверный manual step для текущего gate stage | `Недопустимое действие для текущего этапа подмены раствора.` |
| `irrigation_wait_ready_timeout` | `await_ready` | Зона не вышла в `workflow_phase='ready'` за `AE_IRRIGATION_WAIT_READY_SEC`. |
| `irrigation_recovery_probe_exhausted` | `irrigation_recovery_check` | Исчерпан streak deferred probes IRR-ноды. |
| `emergency_stop_activated` | любая | E-stop активирован, reconcile не подтвердил безопасное состояние. |

## Deprecated коды

Эти коды остаются в `error_codes.json` для совместимости с историческими записями и backlog'ом, но не используются текущим runtime AE3 (`ae3lite/`). Новый код, ссылки в Laravel/UI на эти значения добавлять запрещено.

| Deprecated code | Заменён на |
| --- | --- |
| `ae3_task_create_conflict` | `start_cycle_zone_busy` (active task/lease) или `start_cycle_idempotency_key_conflict` (idempotency race) |
| `ae3_lease_claim_failed` | Провал claim делает silent rollback через `release_claim`; при потере уже захваченной lease — `ae3_zone_lease_lost` |
| `ae3_requeue_failed` | `ae3_transition_apply_failed` / `ae3_poll_apply_failed` / `ae3_correction_apply_failed` |
| `cycle_start_blocked_nodes_unavailable` | `ae3_required_node_offline` / `ae3_snapshot_required_node_type_missing` / `ae3_snapshot_no_online_actuator_channels` / `ae3_snapshot_required_node_persistently_offline` |

## Коды config modes / live-edit (Phase 5–6, HTTP 4xx)

Возвращаются из `ZoneConfigModeController`, `GrowCyclePhaseConfigController`, `ZoneCorrectionLiveEditController`. Коды в API — **snake_case**; в ответе всегда есть `human_error_message`.

| code | HTTP | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `forbidden_set_live` | 403 | Роль не имеет `ZonePolicy::setLive` | `Роль не позволяет переключать зону в live.` |
| `forbidden` | 403 | Нет доступа к зоне или недостаточно прав | `Нет прав на изменение зоны.` / `У вас нет прав...` |
| `config_mode_conflict_with_auto` | 409 | `config_mode='live'` при `control_mode='auto'` | `Нельзя переключить зону в live, пока control_mode=auto.` |
| `ttl_out_of_range` | 422 | `live_until` вне [5 мин, 7 дней] | `TTL должен быть от 5 минут до 7 дней.` |
| `not_in_live_mode` | 409 | extend при `config_mode=locked` | `Продление доступно только в live режиме.` |
| `ttl_total_exceeded` | 422 | суммарный live > 7 дней | `Суммарное время live не может превышать 7 дней...` |
| `ttl_in_past` | 422 | `live_until` в прошлом | `live_until должен быть в будущем.` |
| `zone_not_in_live_mode` | 409 | phase-config / correction при locked | `Редактирование доступно только в config_mode=live.` |
| `no_active_phase` | 409 | нет `current_phase_id` | `У цикла нет активной фазы.` |
| `no_fields_provided` | 422 | пустой whitelist patch | `Передай хотя бы одно поле...` |
| `path_not_whitelisted` | 422 | path вне live-edit whitelist | `Запрошенное поле нельзя менять через live edit.` |
| `calibration_phase_required` | 422 | `calibration_patch` без `phase` | см. каталог |
| `calibration_phase_unknown` | 422 | неизвестный `phase` | см. каталог |
| `zone_not_found` | 404 | zone для grow cycle не найдена | `Зона не найдена.` |
| `phase_not_found` | 404 | `current_phase_id` не существует | `Активная фаза не найдена.` |
| `revision_not_found` | 404 | версия automation config | `Ревизия не найдена.` |

## Коды scheduler cockpit / sync (HTTP 4xx)

| code | HTTP | Контроллер | Когда |
| --- | --- | --- | --- |
| `validation_error` | 422 | `ScheduleExecution*`, webhook HL | невалидный `execution_id` / payload |
| `not_found` | 404 | `ScheduleExecution*` | execution/task не найден |
| `invalid_state` | 409 | `ScheduleExecutionRetryController` | retry не для failed/cancelled |
| `unsupported_task_type` | 422 | retry | только `irrigation_start` |
| `intent_conflict` | 409 | retry | активный intent в зоне |
| `unauthenticated` | 401 | `SyncController`, ingest | нет сессии/токена |
| `internal_error` | 500 | `SyncController` | сбой snapshot |

## Коды Laravel scheduler dispatch и AE3 watchdog

Источник: `backend/laravel/error_codes.json`. Используются в `zone_automation_intents.error_code` и `ae_tasks.error_code` после terminal fail / reap.

| code | Когда | Retryable |
| --- | --- | --- |
| `scheduler_dispatch_connection_error` | Laravel scheduler не достучался до AE3 (`connection_error`, missing response) | да (`retry_count` до `max_retries`) |
| `scheduler_dispatch_http_error` | AE3 вернул non-success HTTP (кроме `409 zone_busy`) | да |
| `scheduler_intent_orphan_pending` | `ae3:reap-stale-tasks`: pending intent без active `ae_task` дольше порога | нет (terminal) |
| `stage_deadline_exceeded` | Watchdog: `stage_deadline_at` истёк | нет |
| `claim_stale` | Watchdog: `claimed` без прогресса | нет |
| `task_progress_stale` | Watchdog: `running`/`waiting_command` без обновления | нет |

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Frontend contract

Frontend показывает ошибку в таком порядке:

1. `human_error_message` из API-ответа (фаза 2 — основной канал).
2. `error_code` / `code` → lookup в `error_codes.json` (`resolveHumanErrorMessage`).
3. Raw-message translation для старых записей и legacy MQTT/AE3 логов.
4. Безопасный fallback `Внутренняя ошибка системы (код: ...)` — **без** показа сырого English.

## Fallback на сырые сообщения

На переходный период сохраняется compatibility mapping для старых сырых сообщений, например:

- `Zone {id} has no online actuator channels`

Новые runtime path не должны генерировать business semantics через raw-message.
