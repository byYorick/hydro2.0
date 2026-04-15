# ERROR_CODE_CATALOG.md
# Канонический каталог кодов ошибок automation/runtime

**Версия:** 1.0  
**Дата:** 2026-03-29  
**Статус:** Актуально  

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
| `ae3_snapshot_no_online_actuator_channels` | `ae3_snapshot` | В зоне нет ни одного online actuator/service channel | `В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.` |
| `ae3_snapshot_conflicting_config_values` | `ae3_snapshot` | Merge runtime-конфига выявил противоречие | `AE3 обнаружил конфликтующие значения в runtime-конфигурации и остановил запуск fail-closed.` |
| `ae3_snapshot_retry_exhausted` | `ae3_snapshot` | Retry на transient snapshot gap исчерпан | `AE3 не смог восстановить transient snapshot gap за допустимое время и завершил задачу с ошибкой.` |
| `ae3_snapshot_retry_persist_failed` | `ae3_snapshot` | Не удалось сохранить повтор retry после transient gap | `AE3 не смог сохранить задачу для повторной попытки после transient snapshot gap.` |
| `unsupported_command_plan_steps` | `ae3_execution` | Planner выдал некорректный набор шагов | `AE3 получил command plan без обязательных шагов и остановил выполнение.` |
| `command_timeout` | `command` | Не пришёл terminal status команды | `Не дождались подтверждения или итогового ответа по команде в допустимое время.` |
| `command_send_failed` | `command` | Не удалось передать команду в transport path | `Команду не удалось отправить до исполнительного узла.` |
| `ae3_task_execution_timeout` | `ae3_execution` | Вся задача превысила runtime timeout | `Выполнение задачи AE3 превысило допустимый runtime timeout.` |
| `ae3_task_execution_unhandled_exception` | `ae3_execution` | Во время выполнения произошло необработанное исключение | `Во время выполнения задачи AE3 произошло необработанное исключение.` |
| `irr_state_unavailable` | `ae3_irr_probe` | Probe IRR-ноды не получил snapshot за `irr_state_wait_timeout_sec` (нода offline / mqtt disconnect / reboot). В polling-стейджах поглощается backoff'ом, эскалируется только при достижении `_IRR_PROBE_FAILURE_STREAK_LIMIT` | `Снимок состояния IRR-ноды недоступен.` |
| `irr_state_stale` | `ae3_irr_probe` | Snapshot получен, но `age > irr_state_max_age_sec`. Семантика как у `irr_state_unavailable` (deferred в polling-стейджах) | `Снимок состояния IRR-ноды устарел.` |
| `irr_state_mismatch` | `ae3_irr_probe` | Snapshot пришёл, но hardware state не совпал с `expected` (valve/pump). **Не** оборачивается backoff'ом — это safety boundary, fail-closed немедленно | `Состояние IRR-ноды не совпало с ожиданиями автоматики.` |
| `irrigation_recovery_probe_exhausted` | `ae3_irr_probe` | В `irrigation_recovery_check` исчерпан streak подряд идущих deferred probes (`_IRR_PROBE_FAILURE_STREAK_LIMIT=5`) — нода долго недоступна | `IRR-нода недоступна: исчерпан лимит подряд идущих probe-deferrals.` |
| `ae3_prepare_recirculation_max_attempts_missing` | `ae3_config` | В bundle коррекции для prepare-recirculation отсутствует обязательный `prepare_recirculation_max_attempts` (Phase 3.1 B-7 fail-closed) | `В конфигурации коррекции отсутствует обязательный параметр числа повторов prepare-recirculation.` |

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
