# ERROR_CODE_CATALOG.md
# Канонический каталог кодов ошибок automation/runtime

**Версия:** 1.1
**Дата:** 2026-05-28
**Статус:** Актуально (sync с runtime кодом 2026-05-28: добавлены ingress/execution/recovery/stage коды, секция deprecated)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Зафиксировать канонический contract для ошибок automation/runtime:

- backend и AE3 передают наружу `error_code`;
- frontend показывает локализованное описание по коду;
- raw `error_message` считается debug-context и запасным каналом без строгого контракта, но не business contract.

Полный машиночитаемый source of truth:

- `backend/error_codes.json`

Производные копии для Laravel/frontend runtime:

- `backend/laravel/error_codes.json`
- `backend/laravel/resources/js/constants/error_codes.json`

## Правила

1. Все новые ошибки automation-engine обязаны иметь стабильный `error_code`.
2. Английский raw-text не может использоваться как ключ ветвления в runtime logic.
3. Если код отсутствует в каталоге, это считается регрессией.
4. Для исторических записей без кода допускается только compatibility fallback локализации.

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

## Таблица кодов irrigation / two-tank stage terminal

Stage-terminal коды используются `WorkflowRouter._fail_task` для безопасного завершения задачи внутри two-tank workflow:

| code | Стадия | Что значит |
| --- | --- | --- |
| `clean_tank_not_filled_timeout` | `clean_fill_check` | Чистый бак не наполнился за `clean_fill_timeout_sec`. |
| `clean_fill_source_empty_stop` | `clean_fill_*` | Источник воды пуст (после повторных попыток). |
| `solution_fill_leak_detected` | `solution_fill_check` | Зафиксирована утечка раствора. |
| `solution_fill_leak_stop` | `solution_fill_*` | Stage остановлен из-за утечки. |
| `solution_fill_source_empty_stop` | `solution_fill_*` | Источник раствора пуст. |
| `solution_fill_timeout_stop` | `solution_fill_check` | Stage timeout / fail-closed по `no-effect`. |
| `prepare_recirculation_solution_low_stop` | `prepare_recirc_*` | Уровень раствора ниже минимального. |
| `prepare_recirculation_attempt_limit_reached` | `prepare_recirc_*` | Исчерпан `prepare_recirculation_max_attempts`. |
| `irrigation_decision_strategy_unknown` | `decision_gate` | Неизвестная irrigation strategy в конфиге. |
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
| `cycle_start_blocked_nodes_unavailable` | `ae3_snapshot_required_node_type_missing` / `ae3_snapshot_no_online_actuator_channels` / `ae3_snapshot_required_node_persistently_offline` |

## Коды config modes (Phase 5, HTTP 4xx/5xx)

Возвращаются из `ZoneConfigModeController` и `GrowCyclePhaseConfigController`. Frontend показывает `data.code` + `data.message`.

| code | HTTP | Когда возникает | Что видит пользователь |
| --- | --- | --- | --- |
| `FORBIDDEN_SET_LIVE` | 403 | Роль не имеет `ZonePolicy::setLive` (только agronomist/engineer/admin) | `Роль не позволяет переключать зону в live.` |
| `FORBIDDEN` | 403 | Пользователь не имеет доступа к зоне или недостаточно прав на update | `Нет прав на изменение зоны.` |
| `CONFIG_MODE_CONFLICT_WITH_AUTO` | 409 | Попытка перейти в `config_mode='live'` при `control_mode='auto'` | `Нельзя переключить зону в live, пока control_mode=auto.` |
| `TTL_OUT_OF_RANGE` | 422 | `live_until` не попадает в [5 минут, 7 дней] от now | `TTL должен быть от 5 минут до 7 дней.` |
| `NOT_IN_LIVE_MODE` | 409 | `PATCH /config-mode/extend` вызван для зоны в locked | `Продление доступно только в live режиме.` |
| `TTL_TOTAL_EXCEEDED` | 422 | Суммарное время от `live_started_at` до `live_until` > 7 дней | `Суммарное время live не может превышать 7 дней от первого включения.` |
| `TTL_IN_PAST` | 422 | `live_until` в прошлом | `live_until должен быть в будущем.` |
| `ZONE_NOT_IN_LIVE_MODE` | 409 | `PUT /grow-cycles/{id}/phase-config` вызван при `config_mode=locked` | `Редактирование активной фазы доступно только в config_mode=live.` |
| `NO_ACTIVE_PHASE` | 409 | У grow cycle не задан `current_phase_id` | `У цикла нет активной фазы.` |
| `NO_FIELDS_PROVIDED` | 422 | Phase-config PUT не содержит whitelisted полей | `Передай хотя бы одно поле из whitelist.` |
| `PATH_NOT_WHITELISTED` | 422 | `PUT /zones/{id}/correction/live-edit` содержит path вне correction/process calibration whitelist | `Запрошенное поле нельзя менять через live edit.` |
| `CALIBRATION_PHASE_REQUIRED` | 422 | Передан `calibration_patch` без `phase` | `Для process calibration укажи phase: generic, solution_fill, tank_recirc или irrigation.` |
| `CALIBRATION_PHASE_UNKNOWN` | 422 | `phase` для `calibration_patch` не входит в допустимый список | `Указан неизвестный phase для process calibration.` |
| `ZONE_NOT_FOUND` | 404 | Zone для grow cycle не найдена | `Zone не найдена.` |
| `PHASE_NOT_FOUND` | 404 | `current_phase_id` указывает на несуществующую phase | `Активная фаза не найдена.` |

## Frontend contract

Frontend показывает ошибку в таком порядке:

1. `human_error_message`, если backend уже прислал локализованное описание.
2. `error_code` -> lookup в `error_codes.json`.
3. Raw-message translation для старых записей.
4. Безопасный fallback `Внутренняя ошибка системы (код: ...)`.

## Fallback на сырые сообщения

На переходный период сохраняется compatibility mapping для старых сырых сообщений, например:

- `Zone {id} has no online actuator channels`

Новые runtime path не должны генерировать business semantics через raw-message.
