---
name: Суточный контур культуры AE3 для ИИ-агентов
description: Последовательный план суточного контура AE3. Поведение, настройки бэка и фронта, наблюдаемость и мониторинг закрываются тестами.
version: 1.2.0
last_updated: 2026-10-04
maintained_by: Hydro 2.0
status: plan
---

# Суточный контур культуры AE3 для ИИ-агентов

**Статус:** план исполнения. Не canonical runtime. Пока этап не отмечен принятым в журнале, поведение кода важнее этого файла.
**Основание:** аудит 2026-10-04 и правка этого плана после ревью. Мастер-план [`AGRO_AUTONOMY_MASTER_PLAN.md`](../AGRO_AUTONOMY_MASTER_PLAN.md), канон [`ae3lite.md`](ae3lite.md).
**Роль исполнителя:** один разработчик Python/Laravel/Vue. Этапы идут строго по порядку. Следующий этап начинается только после зелёных тестов текущего. Другие plan-файлы репозитория не очередь этого поручения: strengthening S0–S8, агроэтапы A–F, roadmap, firmware optimization и climate V2 не начинать.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Какая система считается готовой

Зона с `automation_runtime='ae3'`, рецептом и two-tank (или `single_tank`) без оператора в счастливом пути:

1. Набирает баки, держит pH/EC, доливает бак, включает и гасит свет по фотопериоду. Это уже есть. Повторно не строить.
2. По расписанию поливает. По датчику влажности поливает только при свежем измерении. Нет цели или нет свежего измерения — задача завершается успешным `skip`, насос не стартует, intent не становится `failed`.
3. За местные сутки показывает длительность команд полива, которые дошли до `DONE`. Это длительность, записанная в команду, не показание расходомера. Миллилитры есть только при калибровке канала. Без неё миллилитры пустые.
4. Форточки считают воздушный VPD и точку росы. Без целей VPD проценты открытия не меняются. С целями сухой воздух не добавляет влажностное открытие, а более тёплый и более влажный наружный воздух обнуляет только влажностную добавку. Аварийный перегрев по-прежнему открывает.
5. Если у фазы заданы пределы температуры раствора и датчик обязателен, непрерывный выход за пределы дольше hold блокирует новый полив тем же успешным `skip`. Один свежий образец hold не заменяет. Уже идущая доза не обрывается.
6. Колонка фазы `dli_target` (моль/м²·сутки), если задана, ограничивает яркость внутри фотопериода. Для этого scheduler шлёт дополнительные ON-тики внутри окна. Граница OFF не двигается. Нет ряда PPFD — свет остаётся как сейчас, сутки показывают, что интеграл неизвестен. Автоперевод фазы по DLI не реализуется.
7. Возраст раствора или объём доливов выше порога рецепта даёт одно событие «пора подменить» за сутки. Подмена сама не стартует. Чтение экрана событие не создаёт.
8. На существующем экране зоны виден этот суточный срез. Пустые миллилитры и пустой интеграл не рисуются нулём.
9. Те же пороги оператор задаёт в уже существующих формах зоны, фазы рецепта и климата теплицы. Кривые новые поля API не сохраняет. Уже лежащие в профиле ключи из-за этого не отвергаются. Роли не расширяются.
10. Состояние зоны объясняет отказ полива, неизвестный DLI и подавление влажностного открытия. Текст на русском. Laravel не пересчитывает решение AE.
11. Prometheus считает эти отказы и решения. Grafana показывает их на дашборде automation-engine. Правила алертов есть и в dev, и в prod. `SolutionTempOutOfBand` не копируется.

Приёмка — раздел Definition of Done. Пока он не закрыт, система не называется готовой.

## 2. Что уже сделано и не переписывается

| Контур | Факт | Куда смотреть |
|---|---|---|
| Исполнение task/lease/команд | Поколение claim, атомарный переход, неизменяемая команда | `ae3lite.md`, коммит `a9ac23fd` |
| Граф two-tank / single_tank / drip | `TopologyPack` | `ae3lite/application/services/workflow_topology.py` |
| pH/EC PID, sequential calcium/npk | Работает | `correction.py`, `correction_planner.py` |
| Полив, E-Stop, `await_ready` | Работает. `skip` уже ведёт в `completed_skip` | `decision_gate.py`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` |
| Откат фазы после сбоя полива | `irrigation_start` → `ready` | `workflow_failure_rollback.py` |
| Долив и полуавтоматическая подмена | `solution_topup`, `solution_change` | `AGRO_AUTONOMY_MASTER_PLAN.md` этапы B и D.1 |
| Свет ON/OFF по окну | `lighting_tick`, `desired_state` | `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7 |
| Форточки V1 | `compute_climate_decision`, factors в `greenhouse_automation_state.decision_factors` | `decision_engine.py`, `run_tick.py` |
| Алерты температуры раствора | history-logger, `SolutionTempOutOfBand` | `test_solution_temp_threshold_alerts.py`, `backend/configs/dev/prometheus/alerts.yml` |
| Канал температуры раствора | `solution_temp_c`, domain `temp_water` | `NODE_CHANNELS_REFERENCE.md` §2.4 |
| Колонки фазы | `solution_temp_min`, `solution_temp_max`, `dli_target` | `DATA_MODEL_REFERENCE.md`, фазы рецепта |
| Подсказки состояния зоны | `build_automation_observability` | `ae3lite.md` §9.4 |
| Настройки полива и форточек | Мастер зоны и форма климата | `ZoneAutomationEditWizard.vue`, `GreenhouseClimateConfiguration.vue` |
| Метрики | `ae3_irrigation_decision_total`, дашборд automation-engine | `ae3lite/infrastructure/metrics.py`, `backend/configs/{dev,prod}/` |

Этапы A–F мастер-плана автономии не переоткрывать. Нагреватель раствора, CIP, перевод фазы по DLI (`CONTROL_MODES_SPEC.md` §4.2, заглушка `dli`) и Telegram-токен в этот план не входят.

## 3. Ограничения на все этапы

- Один этап за раз. В журнале раздела 4 записать файлы, команду, exit code, passed/failed. Красный обязательный тест останавливает этап.
- Пайплайн команд: `Laravel scheduler-dispatch → AE → history-logger POST /commands → MQTT`. Прямой MQTT из Laravel и AE запрещён.
- Новые Python-сервисы, новые AE3 `task_type`, новые authority document types, вторая реплика, outbox, редактор графа — запрещены.
- Пороги культуры класть в существующие колонки фазы, `extensions` рецепта или `greenhouse_targets`. Отдельный тип документа authority не создавать.
- Химию PID, коэффициенты и состав доз не менять.
- Запрет полива из-за датчика или температуры раствора — успешный `skip`. Задачу и intent в `failed` из-за этого не переводить. `AE3TaskFailureSpike` на этом не растёт.
- Защищённый контракт сначала правится в `doc_ai/`, затем код. В том же этапе.
- Схема БД — только Laravel-миграция. На `hydro_test` проверять up/down/up только новых миграций. `migrate:fresh`, `reset-db`, `test-db-reset` запрещены. Новая колонка в этом плане не нужна: `dli_target` и `solution_temp_*` уже есть.
- Тесты AE и Laravel на `hydro_test` не запускать параллельно. Интеграции AE — `make test-ae`, не голый pytest в `hydro_dev`.
- Нет цели там, где план требует цель — контур выключен, кроме явно названного fail-closed. Свет без PPFD не гасить.
- Люксы в DLI не переводить. Воздушный VPD не называть VPD листа.
- UI суток — существующий экран зоны. Настройки — существующие формы. Новый дашборд Grafana и новая роль не создаются.
- GET состояния и экрана суток ничего не пишет: ни событие, ни алерт, ни intent.
- Коммит, push, деплой и переключение живой зоны агент не делает, пока человек явно не попросил.

## 4. Журнал

| Этап | Содержание | Статус |
|---|---|---|
| G0 | Сверка, что A–F и ядро исполнения на месте | Принят. Код не менялся. Baseline pytest не запускался, exit code нет |
| G1 | Полив по датчику не стартует без измерения | Принят после ревью. Узкий pytest 14 passed. Интеграционный файл на PostgreSQL повторно не доказан: one-off контейнер получил pg_hba без encryption |
| G2 | Длительность DONE-команд полива за сутки | Принят. PHPUnit `ZoneDayBalanceTest` exit 0, 2 passed |
| G3 | VPD, точка росы, влажностная добавка | Сделан. pytest decision engine exit 0, 25 passed |
| G4 | Температура раствора блокирует новый полив | Сделан. pytest exit 0, 39 passed. PHPUnit не запускался |
| G5 | Потолок `dli_target` внутри фотопериода | Сделан. pytest exit 0, 39 passed. PHPUnit exit 0, 13 passed |
| G6 | Рекомендация подмены без автостарта | Сделан. PHPUnit `SolutionRefreshRecommendationTest` exit 0, 6 passed |
| G7 | Запись и проверка настроек на бэке | Сделан. PHPUnit `CropDaySettingsValidationTest` exit 0, 7 passed |
| G8 | Формы настроек на фронте | Сделан. Vitest exit 0, 7 passed. Typecheck exit 0. Браузер не открывался |
| G9 | Наблюдаемость: подсказки и тексты | Сделан. pytest exit 0, 15 passed. PHPUnit exit 0, 5 passed |
| G10 | Мониторинг: метрики, алерты, Grafana | Сделан. pytest exit 0, 25 passed. PHPUnit `SolutionRefreshRecommendationTest` exit 0, 6 passed. `promtool` нет в PATH |
| G11 | Экран суток на странице зоны | Сделан. Vitest exit 0, 5 passed. Typecheck exit 0. Браузер не открывался |
| G12 | Общий прогон и приёмка | Не закрыт полностью. AE без тома configs: 2 failed / 1709 passed. Те же 2 теста с томом: 2 passed. Laravel 31 passed. HL one-off 5 passed. Vitest 12 passed, typecheck exit 0. YAML E2E и браузер не было |

### Запись G0

Код ради сверки не менялся. `make up`, `migrate:fresh`, `reset-db` не запускались.

Baseline из раздела 5 не запускался: на момент сверки контейнер `automation-engine` не был поднят, `laravel` был unhealthy, а `make test-ae` зависит от `make up`. Exit code не выдумывался.

Факты по коду до правки G1:

- `SmartSoilDecisionStrategy` при пустом окне или `is_stale` возвращал `degraded_run` / `smart_soil_telemetry_missing_or_stale`. Нет min/max и day/night цели тоже давало `degraded_run` / `smart_soil_target_missing`. В `decision_gate` любой исход кроме `skip` и `fail` переходит в `irrigation_start`; `degraded_run` туда и шёл.
- `compute_climate_decision` VPD не считает: открытие — база, температура, влажность и прежние ограничения. `decision.factors` пишутся в `greenhouse_automation_state.decision_factors` (`run_tick.py`).
- `biz_solution_temp_high` / `biz_solution_temp_low` поднимает history-logger (`handlers/solution_temp_threshold_alerts.py` после ingest). `decision_gate` температуру раствора не читает.
- Колонки уже есть: `dli_target` в `recipe_revision_phases` и `grow_cycle_phases`; `solution_temp_min` / `solution_temp_max` — миграция `2026_07_08_120000_add_solution_temp_targets_to_phases.php` на те же две таблицы. Отдельного metric type PPFD нет: единица канала задаётся в его конфиге.

### Запись G1

Файлы: `ae3lite/domain/services/irrigation_decision_controller.py`, `ae3lite/application/handlers/decision_gate.py`, `tests/unit/test_ae3lite_irrigation_decision_controller.py`, `tests/unit/test_ae3lite_irrigation_runtime_integration.py`, `ae3lite.md`.

`test_smart_soil_returns_degraded_run_when_samples_missing` ждал `degraded_run`, потому что пустое или устаревшее окно так и возвращалось, а decision gate вёл это в `irrigation_start`. Ожидание сменено на `skip` / `smart_soil_telemetry_missing_or_stale`: это успешный пропуск, не старт насоса и не `fail`. Мало свежих проб, но не ноль, по-прежнему `run` или `skip` с `degraded=true`, не `degraded_run`.

Команды:

1. `make test-ae PYTEST_ARGS="-q --tb=short tests/unit/test_ae3lite_irrigation_decision_controller.py"` — exit 2. Упал `make up`: `backend-laravel-1 is unhealthy`. Pytest не стартовал. Это не падение тестов G1.
2. Контейнер поднят только для exec (`up -d --no-deps --pull never --no-build automation-engine`, без `make up`) и после прогона остановлен. `docker compose -f backend/docker-compose.dev.yml exec -T -e AE3_PYTEST_DB=hydro_test automation-engine pytest -q --tb=short tests/unit/test_ae3lite_irrigation_decision_controller.py` — exit 0, 14 passed, 0 failed. Процесс сервиса к `hydro_dev` не подключился (`pg_hba`, no encryption) и задачи не забирал.

### Запись G2

Файлы: `backend/laravel/app/Services/ZoneAutomationStateService.php` (`day_balance` в `decorateStatePayload`), `backend/laravel/tests/Feature/ZoneDayBalanceTest.php`, абзац в `REST_API_REFERENCE.md` у контракта `GET /api/zones/{id}/state`. Новой таблицы и endpoint нет. GET только читает.

Команда:

`docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter=ZoneDayBalanceTest`

Exit 0. 2 passed, 16 assertions. `make up`, остановка контейнеров, `migrate:fresh` и запись в `hydro_dev` не выполнялись.

### Запись G3

Файлы: `ae3lite/greenhouse_climate/decision_engine.py`, `tests/unit/test_greenhouse_climate_decision_engine.py`, пропуск `vpd_min_kpa` / `vpd_max_kpa` в `run_tick._greenhouse_targets` (иначе policy затирала цели до решения). Отдельной записи `decision_factors` нет: ключи лежат в `decision.factors`. §8 `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`, одна ссылка в `ae3lite.md` §7.2.2.

Команда:

`docker compose -f backend/docker-compose.dev.yml run --rm --no-deps automation-engine pytest -q --tb=short tests/unit/test_greenhouse_climate_decision_engine.py`

Exit 0. 25 passed, 0 failed. `make up`, остановка контейнеров и `hydro_dev` не использовались.

VPD из теста: 25 °C / 60 % RH → `air_vpd_kpa` 1.267 кПа, точка росы 16.70 °C; тот же прогон, наружные 15 °C / 40 % → `outside_vapor_pressure_kpa` 0.682 кПа. Допуск 0.05 кПа и 0.2 °C. Прежний вход 30 °C / 50 % без целей VPD остаётся 25 % при шаге 25 (`air_vpd_kpa` 2.122).

G4–G12 не отмечались.

### Запись G4

Файлы: `ae3lite/config/schema/runtime_plan.py` (`solution_health`), `ae3lite/config/runtime_plan_builder.py`, `ae3lite/domain/services/solution_temp_irrigation_guard.py`, `ae3lite/application/handlers/decision_gate.py`, `ae3lite/infrastructure/read_models/zone_runtime_monitor.py`, `zone_snapshot_read_model.py`, `effective_targets_sql_utils.py`, `tests/unit/test_ae3lite_solution_temp_irrigation_gate.py`, абзац в `EFFECTIVE_TARGETS_SPEC.md` и `ae3lite.md`. Миграции нет: `required` и `breach_hold_sec` читаются из extensions фазы, min/max — из колонок.

Команда:

`docker compose -f backend/docker-compose.dev.yml run --rm --no-deps automation-engine pytest -q --tb=short tests/unit/test_ae3lite_solution_temp_irrigation_gate.py tests/unit/test_ae3lite_irrigation_decision_controller.py tests/unit/test_ae3lite_runtime_plan_loader.py`

Exit 0. 39 passed, 0 failed. `make up`, остановка контейнеров и `hydro_dev` не использовались.

PHPUnit не запускался: `RuntimePlan` собирает Python `runtime_plan_builder.py`, отдельного PHP builder нет. PHP-часть не отмечена принятой.

G5–G12 на момент записи G4 не отмечались.

### Запись G5

Файлы: `ae3lite/domain/services/dli_integral.py`, `cycle_start_planner.py` (`_build_lighting_tick_plan`), `dli_light_series.py`, `zone_snapshot_read_model.py`, `effective_targets_sql_utils.py`, `ZoneAutomationStateService.php` / `CropDay/DliDayBalance.php`, `SchedulerCycleOrchestrator.php`, `LightingScheduleParser.php`, `EffectiveTargetsService.php`, `EFFECTIVE_TARGETS_SPEC.md`, `DATA_MODEL_REFERENCE.md`, `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7, `NODE_CHANNELS_REFERENCE.md` §2.6, `REST_API_REFERENCE.md`. Новой колонки, `lighting.dli_mol_m2_day`, metric type и task type нет.

Команды:

1. `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps automation-engine pytest -q --tb=line tests/unit/test_ae3lite_cycle_start_planner.py tests/unit/test_ae3lite_compat_start_lighting_tick.py tests/unit/test_ae3lite_dli_lighting.py` — exit 0, 39 passed, 0 failed.
2. `docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter='ZoneDayBalanceTest|DliLightingCheckDispatchTest|LightingScheduleParserTest'` — exit 0, 13 passed, 66 assertions.

Пример: 100 µmol/м²/с × 10 000 с = 1.0 моль/м². Тот же 1.0 в AE `integrate_ppfd` и в PHPUnit `DliIntegral` / `day_balance.dli_mol`. `make up`, остановка контейнеров и `hydro_dev` не использовались.

G6–G12 не отмечались.

### Запись G6

Файлы: `app/Services/CropDay/SolutionRefreshRecommendation.php`, `SchedulerCycleOrchestrator.php` (обход раз в час, если в проходе не было intent полива или долива), `ScheduleDispatcher.php` (сразу после intent `irrigation` / `solution_topup`, до HTTP в AE), `ZoneEventMessageFormatter.php`, `tests/Feature/SolutionRefreshRecommendationTest.php`, абзац в `DATA_MODEL_REFERENCE.md` §8.1. Миграции нет: пороги в `extensions` текущей фазы. Decision gate, GET и `POST /start-solution-change` не пишут событие и не создают intent `solution_change`.

Команда:

`docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter=SolutionRefreshRecommendationTest`

Exit 0. 6 passed, 30 assertions. `make up`, остановка контейнеров и `hydro_dev` не использовались.

G7–G12 не отмечались.

### Запись G7

Файлы: `StoreRecipeRevisionPhaseRequest`, `UpdateRecipeRevisionPhaseRequest` (правила `RecipePhaseRules`, кросс-поля `RecipePhaseTargetValidator`; тот же набор у `StorePlantWithRecipeRequest`). Профиль зоны и климат теплицы пишутся прежним `AutomationConfigController` через `AutomationConfigRegistry`: отдельного Form Request у `PUT /api/automation-configs` нет, новый endpoint не создавался. Стратегия пресетов по-прежнему `StoreZoneAutomationPresetRequest` и `UpdateZoneAutomationPresetRequest`. Спеки: `AUTOMATION_CONFIG_AUTHORITY.md`, `EFFECTIVE_TARGETS_SPEC.md`. Тест: `tests/Feature/CropDaySettingsValidationTest.php`.

`RuntimePlan` собирает Python, в PHP не пересобирался. Фаза читается обратно теми же ключами, включая старый `extensions.legacy_note`. VPD после записи виден в bundle `greenhouse.logic_profile`. Профиль зоны с `lookback`, `hysteresis`, `command_plans` и без новых полей сохраняется. `viewer` по-прежнему получает 403.

Команда:

`docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter=CropDaySettingsValidationTest`

Exit 0. 7 passed, 107 assertions. `make up`, остановка контейнеров и `hydro_dev` не использовались.

G8–G12 не отмечались.

### Запись G8

Файлы: `ZoneAutomationEditWizard.vue` (подпись стратегии), `IrrigationSubview.vue` (та же подпись у кнопок; lookback, stale и hysteresis видны и для `task`), `RecipeEditor.vue` и `recipeEditorShared.ts` (температура раствора, hold, DLI, возраст и объём доливов; пустое поле → `null`), `GreenhouseClimateConfiguration.vue` (`vpd_min_kpa` / `vpd_max_kpa`, подпись «VPD воздуха, не листа», `canConfigure=false` только чтение), `zoneAutomationProfilePayload.ts` (`greenhouseClimateSavePayload` не отдаёт тело запроса, если min VPD не меньше max), `climateParser.ts`, `Greenhouses/Show.vue`, `AutomationStep.vue`, тест `cropDaySettingsForms.spec.ts`. Роли не менялись. Сырой JSON на этих формах не добавлен.

Команды из `backend/laravel`:

1. `npm test -- resources/js/composables/__tests__/cropDaySettingsForms.spec.ts` — exit 0, 7 passed, 0 failed.
2. `npm run typecheck` — exit 0.

Браузер не открывался: сохранение с обновлением страницы, пользователь без права и узкое окно не проверялись. Остаётся Vitest.

G10–G12 не отмечались.

### Запись G9

Файлы: `automation_observability.py` (`irrigation_sensor_blocked`, `solution_temp_blocked` из колонок последней `irrigation_start`), `get_zone_automation_state.py`, `automation_task_repository.py` (`get_last_irrigation_for_zone`). Laravel только проецирует: `ZoneAutomationObservabilityService` дописывает `dli_sensor_unavailable` / `dli_gap` из уже посчитанного `day_balance.dli_status`, `solution_refresh_due` из события `SOLUTION_REFRESH_RECOMMENDED` моложе 24 часов без завершённой подмены после него, `moisture_vent_suppressed` из `decision_factors`. `ZoneAutomationStateService` кладёт `day_balance` до enrich. VPD в PHP нет. Каталоги: `ERROR_CODE_CATALOG.md` (reason skip отдельно от сбоя задачи), `backend/error_codes.json`, `backend/services/automation-engine/error_codes.json`, `backend/alert_codes.json` и синхронные копии Laravel/Android. Спека: `ae3lite.md` §9.4, `API_SPEC_FRONTEND_BACKEND_FULL.md` §3.5.7. Схема `hang_hints` дополнена новыми кодами, старые не менялись.

Пример подсказки:

```json
{
  "code": "irrigation_sensor_blocked",
  "severity": "critical",
  "message": "Полив пропущен: нет свежего измерения влажности. Насос не запускался.",
  "recommendation": "Проверьте датчик влажности и цель в профиле зоны. Это успешный пропуск, не сбой задачи.",
  "details": {
    "reason_code": "smart_soil_telemetry_missing_or_stale",
    "task_id": 42
  }
}
```

Команды:

1. `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps automation-engine pytest -q --tb=short tests/unit/test_ae3lite_automation_observability.py` — exit 0, 15 passed, 0 failed.
2. `docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter=CropDayObservabilityHintsTest` — exit 0, 5 passed, 44 assertions.

`make up`, остановка контейнеров и `hydro_dev` не использовались.

G10–G12 не отмечались.

### Запись G10

Файлы: `ae3lite/infrastructure/metrics.py`, `application/handlers/decision_gate.py`, `greenhouse_climate/run_tick.py`, `domain/services/cycle_start_planner.py`, `CropDay/SolutionRefreshRecommendation.php`, `SchedulerPrometheusMetricsExporter.php`, `backend/configs/{dev,prod}/prometheus/alerts.yml`, `backend/configs/{dev,prod}/grafana/dashboards/automation-engine.json`, `tests/unit/test_ae3lite_crop_day_metrics.py`, `SolutionRefreshRecommendationTest.php`, абзац в `ae3lite.md` §9.4.2. Старые панели Grafana не удалялись. `GreenhouseMoistureVentSuppressed` как alert не заведён.

`ae3_crop_irrigation_blocked_total{reason}` растёт один раз, когда decision впервые вернула blocking skip; повторный poll читает уже записанные колонки задачи. `ae3_irrigation_decision_total` по-прежнему считает каждый проход, `skip` отличим от `run`. VPD — gauge `greenhouse_climate_air_vpd_kpa{greenhouse_id}` на тике, где значение посчитано. Подавление форточки — counter на каждый такой tick. `ae3_dli_tick_total{status}` — один раз на построенный lighting plan. `ae3_solution_refresh_recommended_total` без меток инкрементируется в Laravel после записи события, не из GET; scrape только читает cache.

Telegram фильтрует severity (`critical`/`error`/`warning`), не коды. `solution_refresh_recommended` уже `warning`, тот же маршрут, что `biz_solution_temp_high`. Белый список кодов не вводился. Skip полива в него не добавлялся.

`SolutionTempOutOfBand` до G10 был только в dev (`7d9afd04`). Выражение не менялось: `sum(solution_temp_breach_active) > 0`. Тот же блок добавлен в prod один раз, чтобы в каждом файле правило было ровно одно. Второго правила нет.

`promtool` в PATH нет. Бинарь не ставился.

Команды:

1. `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -v /home/georgiy/esp/hydro/hydro2.0/backend/configs:/hydro-configs:ro automation-engine pytest -q --tb=short tests/unit/test_ae3lite_crop_day_metrics.py tests/unit/test_ae3lite_irrigation_decision_controller.py tests/unit/test_ae3lite_dli_lighting.py` — exit 0, 25 passed, 0 failed. Volume только чтобы pytest увидел YAML и дашборды: в контейнер AE они не смонтированы.
2. `docker compose -f backend/docker-compose.dev.yml exec -T -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter=SolutionRefreshRecommendationTest` — exit 0, 6 passed, 33 assertions.

`make up`, остановка контейнеров и `hydro_dev` не использовались.

G11–G12 не отмечались.

### Запись G11

Файлы: `CropDaySection.vue` (одна секция «Сутки» в `ZoneAutomationRuntimeSection`, без новой страницы), `cropDayView.ts`, `CropDaySection.spec.ts`, прокидка `day_balance` и `decision_factors` в `useAutomationPanel` (раньше нормализатор их выбрасывал), опциональный `recipePhase` с вкладки автоматики для `solution_health.required`, типы в `Automation.ts`, абзац `FRONTEND_UI_UX_SPEC.md` §6.6.2.1. Интеграл, VPD и миллилитры на клиенте не считаются. Если в состоянии зоны нет `air_vpd_kpa`, точки росы и флага подавления, секция пишет «нет снимка климата».

Команды из `backend/laravel`:

1. `npm test -- resources/js/Components/ZoneAutomation/__tests__/CropDaySection.spec.ts` — exit 0, 5 passed, 0 failed.
2. `npm run typecheck` — exit 0.

Браузер не открывался: страница зоны не сверялась с API. Пробел приёмки — живой экран.

G12 не запускался.

### Запись G12

Код продукта не менялся. `make up`, остановка контейнеров, `migrate:fresh`, `reset-db` и запись в `hydro_dev` не выполнялись. Долгоживущий `automation-engine` был Exited; прогон — one-off `run --rm --no-deps`. `conftest.py` форсирует `PG_DB=hydro_test`. База `hydro_e2e` отсутствует. Контейнер `history-logger` в статусе Created, не Up.

Команды:

1. `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps automation-engine pytest -q --tb=line` — exit 1. 2 failed, 1709 passed, 50.67s. Узким фильтром не подменялся.

Хвост:

```
/app/tests/unit/test_ae3lite_crop_day_metrics.py:227: Failed: backend/configs is not visible to this test
/app/tests/unit/test_ae3lite_crop_day_metrics.py:227: Failed: backend/configs is not visible to this test
FAILED tests/unit/test_ae3lite_crop_day_metrics.py::test_dev_and_prod_alerts_keep_one_solution_temp_rule
FAILED tests/unit/test_ae3lite_crop_day_metrics.py::test_dashboards_add_crop_day_panels_without_dropping_old_ones
2 failed, 1709 passed in 50.67s
```

Оба падения — `_configs_dir()` не нашёл `alerts.yml`: в образе AE нет `backend/configs`, том не монтировался. Код не чинился.

Повтор только этих двух тестов с `-v backend/configs:/hydro-configs:ro` и `HYDRO_CONFIGS_DIR=/hydro-configs`: exit 0, 2 passed.

2. Laravel-фильтр `ZoneDayBalanceTest|CropDaySettingsValidationTest|CropDayObservabilityHintsTest|SolutionRefreshRecommendationTest|DliLightingCheckDispatchTest|LightingScheduleParserTest` на `hydro_test`: exit 0, 31 passed, 253 assertions.

3. History-logger контейнер не был Up. One-off `run --rm --no-deps history-logger pytest -q test_solution_temp_threshold_alerts.py`: exit 0, 5 passed. Это не долгоживущий сервис.

4. Из `backend/laravel`: Vitest `CropDaySection.spec.ts` и `cropDaySettingsForms.spec.ts` — exit 0, 12 passed. `npm run typecheck` — exit 0.

5. YAML G1 не входил в этот прогон. Стек e2e и `hydro_e2e` не подняты, сценарий не создавался. Браузерная проверка экрана суток тоже не делалась. Приёмка G12 из-за этого не закрыта.


## 5. G0 — сверка, без нового поведения

Прочитать как контракт, не как список работ: `AGENTS.md`, `backend/services/automation-engine/AGENT.md`, `ae3lite.md` §9.4, `GREENHOUSE_CLIMATE_CONTROL_PLAN.md` §8 (алгоритм форточек; §2.2 и §17 не реализовывать), `EFFECTIVE_TARGETS_SPEC.md`, `NODE_CHANNELS_REFERENCE.md` §2.4 и §2.6, `DATA_MODEL_REFERENCE.md` про `dli_target` и `solution_temp_*`, `API_SPEC_FRONTEND_BACKEND_FULL.md` §3.5.7, `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7. `AGRO_AUTONOMY_MASTER_PLAN.md` не читать ради новых задач. Найти формы `ZoneAutomationEditWizard.vue`, `GreenhouseClimateConfiguration.vue` и редактор фазы рецепта. Найти `SolutionTempOutOfBand` и `AE3TaskFailureSpike`, чтобы их не дублировать и не кормить.

Поднять core (`make up`, если стек лежит) и снять baseline:

```bash
make test-ae PYTEST_ARGS="-q --tb=short tests/unit/test_ae3lite_irrigation_decision_controller.py tests/unit/test_greenhouse_climate_decision_engine.py"
```

Если нужен тест decision gate, взять фактический файл, который его импортирует. Имя `test_ae3lite_handler_decision_gate.py` не выдумывать.

Зафиксировать в журнале:

- `degraded_run` при пустой телеметрии в `SmartSoilDecisionStrategy` доходит до `irrigation_start`.
- `compute_climate_decision` не считает VPD. Factors пишутся в `greenhouse_automation_state.decision_factors`.
- `biz_solution_temp_*` поднимает history-logger. Decision gate полива температуру не читает.
- Колонки `dli_target`, `solution_temp_min`, `solution_temp_max` есть. Нового metric для PPFD нет: единица канала задаётся в его конфиге.

**Приёмка:** журнал содержит команду, exit code и эти факты. Код не менялся.

## 6. G1 — честный полив по датчику

**Проблема.** `smart_soil_v1` без цели или без свежего окна возвращает `degraded_run`. Любой исход кроме `skip` и `fail` идёт в `irrigation_start`. `fail` помечает задачу и intent как сбой и на каждом тике расписания кормит `AE3TaskFailureSpike`.

**Поведение после этапа.** Насос не стартует. Задача завершается уже существующим путём `completed_skip`. Intent остаётся успешным терминалом, не `failed`. Фаза зоны остаётся `ready`.

| Стратегия | Условие | Исход | Насос |
|---|---|---|---|
| `task` | расписание само по себе | `run` | как сейчас |
| `smart_soil_v1` | нет min/max или day/night цели | `skip`, `smart_soil_target_missing` | нет |
| `smart_soil_v1` | нет свежих проб или окно stale | `skip`, `smart_soil_telemetry_missing_or_stale` | нет |
| `smart_soil_v1` | свежие пробы есть, их меньше `min_samples`, полоса посчитана | прежний `run` или `skip` с `degraded=true` | run только если полоса говорит run |
| `force` | как сейчас | не ослаблять | как сейчас |

`degraded_run` для полностью пустого или устаревшего окна больше не возвращать. Отдельный biz-алерт на каждый такой skip не создавать: иначе Telegram получит копию каждого тика. Причина лежит в `ae_tasks.irrigation_decision_outcome=skip` и `irrigation_decision_reason_code`. Подсказку оператору добавляет G9. Счётчик добавляет G10.

**Файлы.** `irrigation_decision_controller.py`, тест `tests/unit/test_ae3lite_irrigation_decision_controller.py`, тест decision gate по фактическому имени. Абзац в `ae3lite.md`: эти reason — успешный skip, не `error_code` задачи. В `ERROR_CODE_CATALOG.md` их как коды сбоя задачи не добавлять.

**Тесты.** Пустая и устаревшая телеметрия дают `skip` и next stage `completed_skip`, не `irrigation_start`. Gateway не проверять: decision gate насос не вызывает. Свежая проба ниже порога даёт `run`. Стратегия `task` без датчика даёт `run`. Задача с этим skip не вызывает `mark_failed`.

**Приёмка:** узкий pytest exit 0. В журнале написано, какой старый тест ждал `degraded_run` и почему ожидание сменено.

## 7. G2 — длительность полива за сутки

**Проблема.** Длительность `DONE` нигде не складывается за день. Складывать все `run_pump` зоны нельзя: тот же cmd есть у набора чистой воды, раствора и рециркуляции.

**Поведение.** Read-model Laravel, без записи и без новой таблицы. Объект `day_balance` на состоянии зоны, которое уже читает экран автоматики:

```text
local_date              дата в timezone теплицы
window_start            местная полночь в UTC
window_end              теперь
timezone_fallback       true только если пояса теплицы нет, окно тогда UTC
irrigation_commands     число подходящих DONE
commanded_sec           сумма commands.duration_ms / 1000
commanded_ml            сумма только при калибровке канала
commanded_ml_status     ok | calibration_missing
```

В сумму входит команда, у которой одновременно:

- статус `DONE`;
- зона этой строки;
- `created_at` внутри окна;
- связь с `ae_tasks.task_type='irrigation_start'` через уже существующий `ae_commands` (`task_id`, `external_id` / `cmd_id`);
- plan key или planner step `irrigation_start`, не `clean_fill_*`, `solution_fill_*`, `prepare_recirculation_*`, `solution_topup_*`.

`commands.duration_ms` — длительность, с которой команда поставлена в history-logger, у тех строк, что дошли до `DONE`. Это не импульс расходомера и не длительность intent, если она разошлась с командой. Поле так и подписывается в API: commanded, не delivered. Нет `duration_ms` — команда считается в `irrigation_commands`, в секунды не входит. Нет калибровки `ml_per_sec` канала — `commanded_ml=null`, статус `calibration_missing`. Ноль вместо null не писать.

Пояс теплицы. Нет пояса — UTC и `timezone_fallback=true`. Одна выборка за окно, не запрос на каждую команду. Политика просмотра зоны та же, что у текущего состояния.

**Файлы.** Существующий Laravel query состояния зоны. Спека ответа в `REST_API_REFERENCE.md` или в контракте Inertia props этого экрана. Колонку не добавлять.

**Тесты.** PHPUnit на `hydro_test`: две DONE `irrigation_start` своей зоны суммируются; DONE `clean_fill_start` и `solution_fill_start` той же зоны не входят; `ERROR` полива не входит; чужая зона не входит; без калибровки `commanded_ml` null; местная полночь отсекает вчера. Фикстура удаляет свои строки.

**Приёмка:** тест exit 0. Ответ API совпадает с прямым SQL по тем же фикстурам.

## 8. G3 — воздух форточек

**Проблема.** Открытие — максимум из базы, температуры и влажности. VPD в плане климата был V2. Считать его нужно из уже существующих температуры и влажности, без новых приводов.

**Формулы.** Температура °C. Влажность перед формулой клампится в `[1, 100]`: ниже 1 берётся 1, выше 100 берётся 100. При отсутствии RH или температуры ключи VPD не пишутся и ноль не подставляется.

```text
es(T) = 0.6108 * exp(17.27 * T / (T + 237.3))     # кПа
ea    = es(T) * RH_clamped / 100
VPD   = es(T_inside) - ea_inside
gamma = ln(RH_clamped / 100) + 17.27 * T / (T + 237.3)
Tdew  = 237.3 * gamma / (17.27 - gamma)
```

В `factors`, когда внутренние T и RH свежие: `air_vpd_kpa`, `dew_point_c`, `inside_vapor_pressure_kpa`. Когда свежа наружная пара: `outside_vapor_pressure_kpa`.

**Порядок решения.** Сначала считаются сегодняшние `base_open_pct`, `temp_open_pct`, `humidity_open_pct`. `outside_hotter_gain` по-прежнему умножает только температурную ветку.

1. Целей `vpd_min_kpa` и `vpd_max_kpa` нет. Factors дописываются, проценты не меняются. Этот снимок фиксируется тестом до правки поведения.
2. Обе цели есть и внутренний воздух свежий. `air_vpd > vpd_max` и температура не ниже `temp_min`: `humidity_open_pct = 0`. `air_vpd < vpd_min`: `humidity_open_pct = max(прежний humidity_open_pct, linear_map(vpd_min - air_vpd, 0..vpd_min, 0..100))`.
3. После пункта 2, если наружные T и RH свежие, `outside_vapor_pressure >= inside_vapor_pressure`, `outside_temp >= inside_temp_median` и нет `emergency_overheat`: `humidity_open_pct = 0`, в factors `moisture_vent_suppressed=true`. `temp_open_pct` и `base_open_pct` этот запрет не уменьшает.
4. Дальше как сейчас: `max(base, temp, humidity)`, затем cold guard, ветер, дождь, min/max. Аварийный перегрев по-прежнему открывает и пункт 3 не применяет.

Спеку `GREENHOUSE_CLIMATE_CONTROL_PLAN.md` §2.2, §8 и §17 поправить здесь: VPD и точка росы входят в расчёт. Прогноз, экраны, отопление, CO₂, туман и температура листа остаются вне плана. В `ae3lite.md` достаточно ссылки.

**Файлы.** `decision_engine.py`, `tests/unit/test_greenhouse_climate_decision_engine.py`, `run_tick.py` только чтобы новые factors попали в уже существующий `decision_factors`. Новый endpoint не создавать.

**Тесты.** Чистые функции. T/RH → VPD и точка росы с допуском 0.05 кПа и 0.2 °C. RH 0 не бросает исключение и не пишет VPD нолём без входа. Без целей VPD проценты на зафиксированном входе прежние. Сухой воздух обнуляет влажностную добавку и не трогает температурную. Наружный воздух теплее и влажнее обнуляет влажностную добавку. Emergency overheat при том же наружном воздухе открывает. Старые тесты ветра и дождя зелёные.

**Приёмка:** файл decision engine exit 0. В журнале пара чисел VPD из теста.

## 9. G4 — температура раствора и новый полив

**Проблема.** History-logger уже поднимает `biz_solution_temp_*`. Новый полив об этом не знает. Нагреватель в этот план не входит. Второй biz-алерт на тот же выход не создавать.

**Поведение.** В `RuntimePlan` блок `solution_health` из колонок фазы `solution_temp_min` / `solution_temp_max` и из extensions фазы:

```text
required          bool, default false
min_c / max_c     колонки фазы
breach_hold_sec   default 600
```

`required=false` или хотя бы один предел пуст: decision gate температуру не смотрит.

`required=true` и оба предела заданы. Исход снова успешный `skip`, не `fail`.

- Нет свежего `solution_temp_c` — `skip`, reason `solution_temp_unavailable`.
- Свежий образец есть, но ряд `telemetry_samples` этого канала за `[now - breach_hold_sec, now]` не покрывает весь интервал или внутри него есть образец внутри полосы — не блокировать. Один `telemetry_last` hold не доказывает.
- Каждый образец этого окна вне `[min, max]`, окно покрыто от начала до конца и дыра между соседними образцами не больше stale сенсора — `skip`, reason `solution_temp_out_of_band`.
- Иначе стратегия G1 работает как раньше.

Stale сенсора для дыры — тот же порог свежести, которым AE уже пользуется для этой телеметрии. Нет готового числа — 600 секунд, не новое обязательное поле.

Проверка в decision gate после стратегии G1 и до `irrigation_start`. Если G1 уже вернула `skip`, температура может заменить reason только когда её собственный `skip` тоже сработал; в журнал пишется один итог. Уже исполняемая доза не отменяется: полив не начался, correction window этого полива не открывается.

**Файлы.** `runtime_plan.py`, `runtime_plan_builder.py`, guard рядом с decision gate, абзац в `EFFECTIVE_TARGETS_SPEC.md` и `ae3lite.md`. Миграцию не писать, колонки на месте. `required` и `breach_hold_sec` — в существующих extensions фазы.

**Тесты.** AE: required, max 24, ряд 30 °C на всём hold → `skip` `solution_temp_out_of_band`, next stage `completed_skip`. Один образец 30 °C без покрытия hold → полив не блокируется температурой. required и нет телеметрии → `solution_temp_unavailable`. required false и нет телеметрии → путь G1. Задача не `failed`. PHPUnit: builder берёт min/max из колонок и `required` из extensions.

**Приёмка:** узкие AE-тесты и один PHPUnit exit 0. `test_solution_temp_threshold_alerts.py` зелёный, его логика остаётся в history-logger.

## 10. G5 — потолок `dli_target`

**Проблема.** `lighting_tick` на границе окна включает свет и больше не смотрит на него до OFF. Колонка `recipe`/`grow_cycle` фазы `dli_target` уже есть. Вторая колонка или ключ `lighting.dli_mol_m2_day` не создаётся. Заглушка автоперевода фазы по DLI в `CONTROL_MODES_SPEC.md` §4.2 не реализуется.

**Единица.** `dli_target` в этом плане — моль/м²·сутки. Это фиксируется в `EFFECTIVE_TARGETS_SPEC.md` и `DATA_MODEL_REFERENCE.md`. Старые строки с непонятной единицей не конвертируются молча: пока цель не задана, поведение света прежнее.

**Какой ряд считать.** Не вводить `metric_type` PAR. Брать уже привязанный к зоне канал света (`NODE_CHANNELS_REFERENCE.md` §2.6, domain `lux_main`, либо наружный канал, если именно он указан в targets света). Единица берётся из конфига канала. В интеграл входят только ряды, у которых единица ровно `ppfd` или `umol_m2_s`. Люкс, пустая единица и смешанный ряд дают `dli_status=sensor_unavailable`. Если этих двух токенов ещё нет в `NODE_CHANNELS_REFERENCE.md`, дописать их там в этом этапе. Новый firmware-драйвер не писать.

**Интеграл.** Считается и в планировщике AE, и в Laravel `day_balance` по одной формуле из этого раздела. Общего писателя нет. AE читает телеметрию сам, в Laravel по HTTP не ходит.

```text
dli_mol = sum(ppfd_umol_m2_s * dt_sec) / 1_000_000
```

`dt_sec` — до следующего образца, не больше `dli_stale_gap_sec`. Дефолт дыры 600 секунд. Дыра больше этого рвёт интеграл: `dli_status=gap`, яркость этого тика не режется. Ряды старше местных суток и чужие зоны не входят. Пример приёмки: 100 µmol/m²/s ровно 10 000 с = 1.0 моль/м².

**Тики.** OFF на границе окна не меняется. Если `dli_target` задан, существующий lighting dispatcher дополнительно шлёт `desired_state=on` внутри открытого окна не чаще чем раз в `dli_check_interval_sec` (дефолт 900) через уже существующий `POST /zones/{id}/start-lighting-tick`. Это не новый task type. Idempotency key включает бакет интервала. `409 zone_busy` по-прежнему не двигает курсор OFF. Если цель пуста, дополнительных тиков нет.

**Яркость одного ON-тика.**

| Условие | Duty | `dli_status` |
|---|---|---|
| `dli_target` пуст | как сейчас | `not_configured` |
| цель есть, ряда PPFD нет | как сейчас, свет не гасить | `sensor_unavailable` |
| цель есть, дыра в ряде | как сейчас | `gap` |
| интеграл без дыр уже ≥ цели | duty 0 на этом ON | `capped` |
| интеграл ниже цели | не выше запрошенного `brightness_pct` | `within_target` |

Добирать яркость выше рецепта нельзя. `sensor_unavailable` даёт не больше одного biz-алерта `dli_sensor_unavailable` на зону за местные сутки. Пишет его планировщик тика, не GET экрана.

**Файлы.** `cycle_start_planner.py` `_build_lighting_tick_plan`, dispatcher света в Laravel, `day_balance` из G2 (поля `dli_mol`, `dli_status`), `EFFECTIVE_TARGETS_SPEC.md`, один абзац в `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7, `NODE_CHANNELS_REFERENCE.md` только для имён единиц. Каталоги алертов — в G9, здесь только код и один тест, что повтор за сутки не плодит второй алерт.

**Тесты.** OFF остаётся duty 0 независимо от интеграла. ON при интеграле выше цели даёт duty 0. ON ниже цели сохраняет яркость запроса. Люкс не становится молями. Дыра не обнуляет duty. Числовой пример 1.0 моль есть и в AE, и в PHPUnit read-model. Dispatcher с пустым `dli_target` не добавляет средний тик. С заданной целью ключ бакета стабилен на повторе.

**Приёмка:** тесты света и оба расчёта интеграла exit 0. В журнале пример 100 × 10 000 с = 1.0.

## 11. G6 — рекомендация подмены

**Проблема.** `solution_change` запускает только оператор. Система не говорит, что раствор старый. Писать это из GET нельзя.

**Поведение.** Пороги в extensions фазы, оба необязательные:

```text
solution_max_age_days            int 1…60
solution_refresh_after_topup_ml  number > 0
```

Оба пустые — событие не создаётся.

Возраст считается от последнего успешного завершения `solution_change` или, если его не было, от последнего перехода зоны в `ready` после `cycle_start`. Объём доливов — сумма `DONE` команд долива с того же момента, plan key `solution_topup`, теми же правилами калибровки, что G2. Порог превышен и за последние 24 часа события `SOLUTION_REFRESH_RECOMMENDED` ещё нет → одно zone event и один biz-alert.

Владелец записи один: существующий проход Laravel scheduler-dispatch, рядом с созданием intent полива или долива, до вызова AE. Если в этом проходе intent не создаётся, отдельный обход зон раз в час допустим только внутри уже запущенной scheduler-команды. Decision gate AE это событие не пишет. GET его не пишет. `POST /start-solution-change` не вызывается, intent `solution_change` не создаётся.

**Тесты.** Возраст старше порога создаёт одно событие. Повтор через час не создаёт второе. Ниже порога события нет. После события список intent `solution_change` пуст. Вызов read-model суток не увеличивает число событий.

**Приёмка:** тест exit 0.

## 12. G7 — настройки на бэке

**Проблема.** G4–G6 читают пороги, а запись оператора ещё не проверяет новые поля. Проверять «весь JSON профиля» нельзя: в `zone.logic_profile` уже лежат lookback, hysteresis и command plans.

**Поведение.** Тот же API authority и климата. Новый endpoint не создавать. Form Request проверяет только новые поля. Неизвестный старый ключ сохраняется как сегодня.

| Поле | Где | Правило |
|---|---|---|
| стратегия `task` \| `smart_soil_v1` | профиль зоны, как сейчас | иное значение — 422, остальные ключи не из-за этого |
| `solution_health.required`, `breach_hold_sec` | extensions фазы | `required=true` только вместе с обоими колонками min/max; hold 60…86400; отсутствие ключей — контур выключен |
| `dli_target` | уже существующая колонка фазы | пусто или число > 0 и ≤ 100 |
| `solution_max_age_days` | extensions фазы | пусто или целое 1…60 |
| `solution_refresh_after_topup_ml` | extensions фазы | пусто или число > 0 |
| `vpd_min_kpa`, `vpd_max_kpa` | `greenhouse_targets` | оба пустые или оба заданы, каждый 0.1…3.0, min < max |

Пустое поле — контур выключен, не ноль. `runtime_plan_builder` и сборщик климата читают эти поля и не выкидывают остальные ключи профиля. Горячая смена попадает в следующий полив и следующий climate tick тем же путём, что сегодняшние цели.

Авторизация прежняя. Роли не менять.

**Файлы.** Form Request, которые уже пишут профиль зоны, фазу и климат. Спеки `AUTOMATION_CONFIG_AUTHORITY.md` и `EFFECTIVE_TARGETS_SPEC.md`. `vendor/bin/pint --dirty` на затронутом PHP.

**Тесты.** Валидные значения после пересборки видны в `RuntimePlan` или в bundle климата. min > max, отрицательный `dli_target`, только один из двух VPD дают 422 и не пишут документ. Профиль с прежними ключами полива и без новых полей сохраняется. Роль, которой update был закрыт раньше, по-прежнему получает отказ.

**Приёмка:** тесты валидации exit 0. В журнале имена Form Request.

## 13. G8 — формы настроек

**Проблема.** Пороги G7 нельзя включить с экрана.

**Поведение.** Три уже существующих места.

1. `ZoneAutomationEditWizard.vue`. Подпись у стратегии: `task` поливает по расписанию; `smart_soil_v1` без свежей влажности пропускает полив и не помечает задачу сбоем. Поля lookback, stale и hysteresis не прятать.
2. Редактор фазы рецепта, рядом с целями pH/EC и светом. Поля: обязательность температуры раствора, min/max если их на форме ещё нет, hold в секундах, `dli_target` моль/м²·сутки, возраст раствора в днях, объём доливов до рекомендации. Пустое поле отправляет `null`. Подпись у DLI: нужен канал с единицей PPFD, люксы не пересчитываются, и что при заданной цели внутри окна появятся проверочные тики света.
3. `GreenhouseClimateConfiguration.vue`. Два поля VPD, кПа. Подпись: VPD воздуха, не листа. Оба пустые или оба заполнены. `canConfigure=false` оставляет поля только для чтения.

Подсказки на русском. Сырой JSON на этих формах не показывать.

**Тесты.** Vitest: пустой DLI не становится 0; min VPD больше max не уходит в запрос; стратегия `smart_soil_v1` показывает текст про пропуск без датчика. Typecheck затронутых файлов.

**Проверка в браузере.** Пользователь с правом конфигурации сохраняет каждую группу, обновляет страницу и видит те же числа. Пользователь без права поля не редактирует. Узкое окно не перекрывает сетку. Если браузера нет — назвать пробел и оставить Vitest.

**Приёмка:** Vitest и браузерная проверка. Сохранённое значение читается тем же API.

## 14. G9 — наблюдаемость

**Проблема.** Успешный skip виден в строке задачи, но не в состоянии зоны. Новый код без русского текста оператор не поймёт.

**Поведение.** Laravel не принимает решение заново и не считает VPD в PHP.

| Что видит оператор | Откуда читается | Кто решил |
|---|---|---|
| `irrigation_sensor_blocked` | последняя задача полива: outcome `skip` и reason `smart_soil_target_missing` или `smart_soil_telemetry_missing_or_stale` | AE, колонки `ae_tasks` |
| `solution_temp_blocked` | тот же skip с reason `solution_temp_out_of_band` или `solution_temp_unavailable` | AE |
| `dli_sensor_unavailable`, `dli_gap` | `day_balance.dli_status` | расчёт G5, не новый решатель |
| `solution_refresh_due` | событие `SOLUTION_REFRESH_RECOMMENDED` моложе 24 часов и подмена после него не завершена | событие G6 |
| `moisture_vent_suppressed` | `greenhouse_automation_state.decision_factors` теплицы этой зоны | AE climate tick |

Подсказки AE-решений собирает `build_automation_observability` из колонок задачи. Подсказки DLI, подмены и форточки Laravel дописывает в тот же payload как проекцию уже записанных строк. Если строки нет, подсказку не выдумывать. На stale-cache не подменять их чужим расчётом. Severity: блокировки полива `critical`, DLI и подмена `warning`, подавление форточки `info`.

Каталоги, все затронутые, одним смыслом: `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` (reason skip описать отдельно от кодов сбоя задачи), `backend/services/automation-engine/error_codes.json`, `backend/error_codes.json`, `backend/alert_codes.json`. У biz-кодов `dli_sensor_unavailable` и `SOLUTION_REFRESH_RECOMMENDED` русский заголовок и действие. Секреты и SQL в текст не класть.

Спека: `ae3lite.md` §9.4 и `API_SPEC_FRONTEND_BACKEND_FULL.md` §3.5.7. Старые hint-коды не менять.

**Тесты.** Unit AE: skip по влажности даёт одну подсказку `irrigation_sensor_blocked`; здоровый `run` её не даёт. PHPUnit: проекция читает `decision_factors.moisture_vent_suppressed` и не считает VPD; отсутствие factors не создаёт подсказку; stale-cache не затирает hint, которого не было во входном payload. Новые biz-коды есть в JSON каталога.

**Приёмка:** тесты exit 0. В журнале один пример payload подсказки.

## 15. G10 — мониторинг

**Проблема.** Дашборд уже рисует `ae3_irrigation_decision_total`. Новые skip и VPD туда не попадут сами. `SolutionTempOutOfBand` уже смотрит `solution_temp_breach_active`.

**Метрики.** В метку не писать текст ошибки и payload. `zone_id` в метки не писать.

| Метрика | Когда растёт | Метки |
|---|---|---|
| `ae3_irrigation_decision_total` | как сейчас, outcome `skip` уже отличим от `run` | существующие |
| `ae3_crop_irrigation_blocked_total` | один раз на задачу, когда decision впервые вернула блокирующий skip | `reason`: `smart_soil_target_missing`, `smart_soil_telemetry_missing_or_stale`, `solution_temp_out_of_band`, `solution_temp_unavailable` |
| `greenhouse_climate_air_vpd_kpa` | на тике, где VPD посчитан | `greenhouse_id` |
| `greenhouse_climate_moisture_vent_suppressed_total` | один раз на climate tick, если flag true | `greenhouse_id` |
| `ae3_dli_tick_total` | один раз на построенный lighting plan | `status`: `not_configured`, `sensor_unavailable`, `gap`, `capped`, `within_target` |
| `ae3_solution_refresh_recommended_total` | один раз на записанное событие G6 | без меток |

Повторный poll той же задачи счётчик блокировки не крутит. Climate counter растёт на каждый подходящий tick: это не «один раз навсегда».

**Алерты.** Одинаковый текст в `backend/configs/dev/prometheus/alerts.yml` и `backend/configs/prod/prometheus/alerts.yml`.

| Alert | Выражение | Зачем |
|---|---|---|
| `AE3SmartSoilBlocked` | `sum(increase(ae3_crop_irrigation_blocked_total{reason=~"smart_soil_.+"}[15m])) > 0`, `for: 0m`, severity warning | один блокирующий skip уже значит, что датчик стратегии молчит |
| `AE3DliSensorMissing` | `sum(increase(ae3_dli_tick_total{status="sensor_unavailable"}[1h])) > 0`, `for: 1h`, severity warning | тики и так бывают только когда диспетчер света жив; отдельные «дневные часы» не кодировать |

`GreenhouseMoistureVentSuppressed` как alert не заводить: это штатное решение, только панель. `SolutionTempOutOfBand` не копировать и не менять его выражение.

Новый biz-код подмены идёт в Telegram тем же маршрутом, что `biz_solution_temp_high`, если маршрут — белый список. Отдельный бот не создавать. Skip полива в этот белый список не добавлять.

**Grafana.** В `automation-engine.json` dev и prod, старые панели не удалять: доля исходов полива, блокировки по `reason`, VPD по `greenhouse_id`, статусы DLI, счётчик рекомендаций подмены. Выражения ссылаются только на метрики этой таблицы.

**Тесты.** Один блокирующий skip увеличивает counter с полным reason `smart_soil_telemetry_missing_or_stale` и decision counter с `skip`. Второй poll той же задачи blocked counter не увеличивает. Оба YAML содержат два новых alert и по-прежнему ровно один `SolutionTempOutOfBand`. Если в PATH есть `promtool`, `promtool check rules` на обоих файлах. Если нет — записать это в журнал и не ставить бинарь.

**Приёмка:** unit метрик exit 0, YAML согласованы, панели ссылаются на эти метрики.

## 16. G11 — экран суток

**Проблема.** Оператору видны команды, не сутки культуры.

**Поведение.** На уже существующей странице зоны, в блоке автоматики, секция «Сутки»:

- дата и пояс, пометка если пояс свалился в UTC;
- число команд полива и `commanded_sec`;
- `commanded_ml` или текст «нет калибровки канала», не ноль;
- свет: фотопериод, яркость, `dli_mol` или статус `not_configured` / `sensor_unavailable` / `gap`;
- климат: последний `air_vpd_kpa`, точка росы и флаг подавления из `decision_factors`, если строка состояния теплицы есть;
- раствор: последняя температура, включён ли gate G4, есть ли рекомендация подмены;
- подсказки G9 текстом каталога, не сырым reason;
- первые сутки без команд: `irrigation_commands=0`, миллилитры null, не смесь нулей и ошибки запроса.

Числа только из read-model. На клиенте интеграл не пересчитывать.

**Файлы.** Vue-страница зоны и её Inertia props. Один компонент. Vitest: пусто, нет калибровки, DLI недоступен, текст блокировки полива. Интерфейс на русском.

**Проверка в браузере.** Открыть страницу зоны, дойти до секции, сверить числа с API. Узкое окно. Если браузера нет — назвать пробел.

**Приёмка:** Vitest и typecheck exit 0. Браузерная проверка сделана или пробел назван.

## 17. G12 — приёмка всей системы

Обязательные команды, по одной, на `hydro_test`.

```bash
make test-ae PYTEST_ARGS="-q --tb=short"
```

Laravel, с `APP_ENV=testing` и `DB_DATABASE=hydro_test`:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T \
  -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test \
  --filter="Ae3Lite|GreenhouseClimate|ScheduleDispatcher|DayBalance|SolutionHealth|LightingTick|CropDaySettings|AutomationObservability"
```

Фильтр сузить до реальных имён классов этого плана. Не запускать весь `php artisan test`, если фильтр покрывает новые тесты и соседние контракты климата, полива и света.

History-logger:

```bash
docker compose -f backend/docker-compose.dev.yml exec -T history-logger \
  pytest -q test_solution_temp_threshold_alerts.py
```

Frontend из `backend/laravel`: `npm run typecheck` и Vitest форм настроек и компонента суток.

YAML E2E — один новый сценарий рядом с `tests/e2e/scenarios/ae3lite/`. Он проверяет только G1: стратегия `smart_soil_v1`, телеметрии влажности нет, команды `run_pump` плана `irrigation_start` нет, задача не в `failed`. Перед запуском прочитать `tests/e2e/AGENTS.md` и `doc_ai/13_TESTING/E2E_GUIDE.md`. Узкий сценарий, не `--set=full`. Стек `e2e`, база `hydro_e2e`. Realhw не входит в приёмку.

VPD, DLI, валидация настроек, сутки и метрики этот YAML не покрывает. Их приёмка — unit и feature тесты своих этапов. Так и записать в журнале G12, не называя один сценарий проверкой всего контура.

Журнал G12 хранит exit code каждого обязательного прогона. Skip, пустой набор и отсутствие Docker успехом не считаются.

## 18. Definition of Done

- [ ] G1: нет свежей влажности → `completed_skip`, насос не стартует, intent не `failed`. Расписание без датчика поливает.
- [ ] G2: в сумму входят только DONE плана `irrigation_start`. Набор бака не входит. Без калибровки миллилитры null. Секунды — это `duration_ms` команды.
- [ ] G3: без целей VPD проценты прежние. С целями сухой воздух и влажный тёплый наружный воздух обнуляют только влажностную добавку. Перегрев открывает. RH 0 не роняет расчёт.
- [ ] G4: hold доказан рядом образцов. Один образец не блокирует. Обязательный мёртвый датчик даёт skip. Нагревателя нет, второй biz-алерт температуры не появился.
- [ ] G5: используется колонка `dli_target`. Люкс не конвертируется. OFF фотопериода на месте. При заданной цели есть проверочный ON-тик внутри окна. Фаза по DLI сама не переводится.
- [ ] G6: рекомендация одна в сутки, не из GET, intent подмены не создаётся.
- [x] G7: кривые новые поля дают 422. Старый профиль без новых ключей сохраняется.
- [ ] G8: формы зоны, фазы и климата пишут эти поля и показывают их после обновления.
- [x] G9: подсказка блокировки читает skip задачи. Форточка читает `decision_factors`. PHP VPD не считает.
- [x] G10: reason метрики совпадает с reason skip. У VPD есть `greenhouse_id`. Новые алерты есть в dev и prod. `SolutionTempOutOfBand` один.
- [x] G11: экран показывает commanded-секунды, пустые миллилитры и текст блокировки. Vitest и typecheck зелёные. Браузер не открывался.
- [ ] G12: полный AE, фильтр Laravel, HL-тест температуры, Vitest и один узкий YAML зелёные. В журнале сказано, что YAML закрывает только G1.
- [ ] Спеки затронутых контрактов обновлены в тех же этапах. Новых сервисов, task type, metric type и ролей нет.
- [ ] Журнал заполнен командами и числами.

## 19. Запрещено в рамках этого плана

Ион-селективные электроды, перевод EC в отдельные ионы, прогноз погоды, экраны, отопление, CO₂, туман, температура листа, bang-bang нагревателя раствора, автозапуск `solution_change`, перевод lux→PPFD, автоперевод фазы по DLI, ML и digital-twin, новая реплика AE, правка PID, новая роль, новый дашборд Grafana с нуля, второй бот Telegram, дубль `SolutionTempOutOfBand`, `fail` задачи из-за мёртвого датчика влажности или температуры раствора, сумма всех `run_pump` зоны как «полив», запись события из GET.

## 20. Промпт исполнителю

Скопировать целиком:

> Выполни по порядку G0–G12 из `doc_ai/04_BACKEND_CORE/AE3_CROP_DAY_LOOP_PLAN_FOR_AI_AGENTS.md` версии 1.2.0. Один этап за раз. Сначала спека затронутого контракта, потом код, потом тесты этапа. Обнови журнал: файлы, команда, exit code, passed/failed. Не начинай следующий этап при красном тесте. Запрет полива из-за датчика — успешный skip, не failed task. В воду суток бери только DONE плана irrigation_start. DLI читай из колонки dli_target, люксы не конвертируй. Событие подмены не пиши из GET. Старые ключи logic_profile не отвергай. Метрики и алерты обнови и в dev, и в prod. Не добавляй сервис, task type, metric type, authority document type и роль. Не переписывай PID, lease и фотопериод OFF. Коммит и деплой не делай.
