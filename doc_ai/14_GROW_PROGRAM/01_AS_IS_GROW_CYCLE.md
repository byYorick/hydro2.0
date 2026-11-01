# Как сейчас устроен цикл выращивания

**Статус:** `plan` (описание кода на `ff796c3c`, не новый контракт)  
**Дата:** 2026-11-01

Иерархия домена: теплица → зоны → узлы → каналы. Один Laravel обслуживает много теплиц (`Greenhouse` → зоны). На зону в AE3 допускается одна активная задача (partial unique index `ae_tasks`, lease).

## Поток команд

Штатный путь:

`Laravel scheduler-dispatch` → строка в `zone_automation_intents` → HTTP в automation-engine → задача `ae_tasks` (`pending → claimed → running → waiting_command → completed|failed`) → `HistoryLoggerClient` `POST /commands` → history-logger пишет `QUEUED`, подписывает HMAC и публикует MQTT `hydro/{gh}/{zone}/{node}/{channel}/command` → узел отвечает `command_response` → AE3 опрашивает таблицу `commands`.

Прямой MQTT-publish команд из каталога `ae3lite/` нет. Единственная штатная точка публикации — history-logger.

Отдельный операторский путь минует AE3: `PythonBridgeService` шлёт тот же history-logger (`backend/laravel/app/Services/PythonBridgeService.php`, метод отправки зональной команды около строк 153–180). Подпись Laravel history-logger всё равно отбрасывает и подписывает сам.

Типы задач, которые реально есть в схеме AE3 (`laravel_schema_contract.py`): `cycle_start`, `irrigation_start`, `lighting_tick`, `solution_topup`, `solution_change`, и отдельно `greenhouse_climate_tick`. Новые `task_type` этим планом не вводятся.

## Рецепт и фаза

Модель фазы — `RecipeRevisionPhase` (`backend/laravel/app/Models/RecipeRevisionPhase.php`). Колонки уже умеют pH/EC (target/min/max), программу питания (доли NPK/Ca/Mg/micro, дозы мл/л, режим дозирования), режим полива, интервал и длительность, фотопериод и время включения, температуру воздуха, влажность, CO2, температуру раствора, DLI, стратегию смены фазы (`time`, а в схеме ещё `gdd` / `dli` / `ai` / `manual_only`), `extensions`.

Цикл зоны создаёт `GrowCycleService`. Снимок фазы копируется в `grow_cycle_phases`. Смена фазы по времени — команда `phases:auto-advance` (`AutoAdvancePhases.php`): в выборку попадает только `phase_advance_strategy = time`. На последней фазе цикл не прыгает сам, оператору остаётся событие на ревизию. GDD и DLI как автоперевод фазы в этой команде не исполняются.

pH/EC-цели контроллера берутся из активной фазы рецепта. Нет цели — коррекция fail-closed (`PlannerConfigurationError`), жёстких дефолтов нет.

## Гидравлика и полив

Пакеты топологий (`ae3lite/application/services/workflow_topology.py`):

| Пакет | Смысл |
|-------|--------|
| `two_tank` | Полный граф: чистая вода, раствор, рециркуляция подготовки, полив |
| `two_tank_drip_substrate_trays` | Тот же граф, привязка полива `drip_substrate_trays` |
| `single_tank` | Тот же граф без ветки чистого бака |
| `generic_cycle_start` | Диагностика, не агроцикл |
| `lighting_tick` | Пакет команд света |

Отдельных графов NFT, DWC, ebb-and-flow, аэропоники нет. Эти имена живут как `irrigation_system_type` пресета и как вывод `RECIRC → nft`, `SUBSTRATE → drip` в сидерах. Для капли на субстрате боевой пакет — `two_tank_drip_substrate_trays` (два бака и четыре поплавка) либо `single_tank`, если чистого бака нет.

Граф two-tank включает набор баков, коррекцию на заполнении и рециркуляции, полив, долив (`solution_topup`) и подмену раствора. Подмена — полуавтомат: стадии `await_operator_drain_confirm` и `await_operator_refill_confirm`. Сама подмена по событию «пора сменить раствор» не стартует (суточный контур G6).

Полив по расписанию ставит Laravel (`automation:dispatch-schedules`, `ScheduleDispatcher`). Интервал и длительность читаются из фазы. Решение «пустить насос» принимает `IrrigationDecisionController`: стратегия по задаче (длительность) или `smart_soil_v1`. Для почвы без свежего измерения задача завершается успешным `skip`, насос не стартует. Объём в миллилитрах считается только из калибровки канала и длительности команды `DONE`. Расходомера и доли дренажа в решении AE3 нет: `drain_target_percent` лежит в `extensions` богатых сидеров и в рантайм полива не входит.

Прошивка полива `storage_irrigation_node`: насос `pump_main`, клапаны чистого наполнения, чистой подачи, наполнения раствора, подачи раствора, полива; датчики `level_clean_min/max`, `level_solution_min/max`. Команда — `set_relay`, для насоса ещё алиас `run_pump`. Клапана дренажа на этой ноде нет (`valve_drain` упомянут в README и отсутствует в карте каналов). E-STOP — GPIO этой ноды: пока кнопка зажата, ON отвергается; после отпускания актуаторы остаются выключенными, но флаг `g_estop_active` сбрасывается (`storage_irrigation_fw_fail_safe.c`, переход release).

## Коррекция pH и EC

`ph_node`: датчик Trema pH, насосы `pump_acid` и `pump_base`, команды `dose` / `run_pump` / `calibrate`. Канал `solution_temp_c` объявлен в карте, но `test_sensor` отвечает `sensor_unavailable` («Solution temperature sensor is not configured in firmware»). Телеметрия температуры раствора с этой ноды не публикуется.

`ec_node`: Trema EC, четыре насоса `pump_a`…`pump_d` (в документации каналов: NPK, кальций, магний, микро). Температура модуля Trema используется для компенсации EC и наружу как `solution_temp_c` не отдаётся.

AE3 ведёт PID по измеренным pH и EC. Последовательный пайплайн подготовки раствора (кальций, pH, магний, NPK, микро) привязан к стадиям two-tank, а не к колонке `nutrient_*_dose_ml_l`. Эти колонки сидер заполняет, рантайм AE3 по ним дозу не строит. Потолок одной дозы — 60 000 мс. Три `no-effect` подряд по одному `pid_type` закрывают окно коррекции.

## Свет

`lighting_tick` строит ON/OFF по окну фотопериода. Если у фазы задан `dli_target` и есть ряд PPFD, яркость внутри окна ограничивается; граница OFF не сдвигается. Нет ряда PPFD — свет остаётся как есть, интеграл помечается неизвестным. Команда на канал: `set_pwm` или `set_relay` (`cycle_start_planner.py`, `_lighting_cmd_for_channel`).

`light_node` измеряет только люксы (Trema light, метрика `LIGHT`). Актуатора, `set_relay` и `set_pwm` на ней нет. Включить лампу этой нодой нельзя. ШИМ в прошивке есть у `climate_node`, если канал актуатора пришёл в NodeConfig.

## Климат

Тепличный тик (`ae3lite/greenhouse_climate/`) считает открытие форточек: база, температура, влажность, VPD воздуха и точка росы. Команда на каналы `roof_vent_left` / `roof_vent_right` — `set_position` с `position_pct`. В прошивках `set_position` не реализован. Нагреватель, осушитель, приток CO2 и экран затенения отдельными решениями тика не управляются.

`climate_node` меряет SHT3x (температура и влажность) и CCS811 (канал `co2`; это оценка eCO2, не оптический датчик). Актуаторы не зашиты: `set_relay` и `set_pwm` регистрируются и работают по каналам из NodeConfig (роли вроде RELAY, FAN, HEATER, LED). Люкса и форточек в коде ноды нет.

Тип теплицы в UI создания: `indoor`, `greenhouse`, `outdoor`. Рецепты расширенного сидера помечены `site_type = indoor` и `season = all_year`. Отдельной логики «открытый грунт» и «досветка только когда солнца мало» нет.

## Алерты и интерфейс оператора

События пишутся в `zone_events` / алерты. Живые контуры, которые видны в коде суточного плана и сервисов: выход температуры раствора (history-logger, `SolutionTempOutOfBand`), рекомендация подмены раствора раз в сутки, пропуск полива из-за датчика или температуры раствора, метрики Prometheus и дашборд automation-engine. Каталог содержит коды вроде `biz_light_failure` и `biz_dry_run`; излучателя в AE3 для света нет, проверка сухого хода `water_flow.check_dry_run_protection` в `ae3lite/` не вызывается.

Операторский UI — Unified Dashboard и страницы зоны: мастер автоматики, редактор рецепта (температура раствора, DLI, возраст раствора), климат теплицы (VPD воздуха), суточный срез `day_balance` (длительность полива, миллилитры только при калибровке, DLI). Android (`mobile/app/android`): логин, список теплиц и зон, телеметрия, алерты, общий `sendCommand`, заготовка провижининга. Экрана цикла, фазы и рецепта нет. Токен лежит в обычном Preferences DataStore, в манифесте `usesCleartextTraffic="true"`.

## Что уже можно считать рабочим ядром

Для зоны с `automation_runtime=ae3`, опубликованным рецептом и узлами полива, pH и EC код умеет: набрать баки по поплавкам, держать pH/EC дозированием, доливать бак, полить по интервалу фазы, пропустить полив без свежей влажности, включить и выключить свет командой реле или ШИМ на той ноде, где канал актуатора реально есть, посчитать VPD и желаемый процент форточки. Суточный контур G0–G11 в журнале плана отмечен сделанным; общий прогон G12 (YAML E2E и браузер) не закрыт.

Этого недостаточно, чтобы без доработок поставить живую каплю в сезонной крымской теплице. Разрыв — в [02_GAP_ANALYSIS.md](02_GAP_ANALYSIS.md).
