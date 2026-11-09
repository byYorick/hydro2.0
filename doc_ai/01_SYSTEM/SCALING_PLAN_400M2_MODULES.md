# SCALING_PLAN_400M2_MODULES.md
# План масштабирования: теплица 20 м² → модуль 400 м² → N модулей, все типы гидропоники

**Версия:** 0.1
**Дата:** 2026-11-09
**Автор:** архитектурный обзор (Grok Bot), черновик для ревью владельцем
**Статус:** `planned` — дорожная карта. Не SoT runtime, не контракт. Поведение runtime — код
(см. [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md)).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Документ сам ничего не меняет в протоколе; изменения контрактов, перечисленные ниже, требуют
doc-first правки соответствующих защищённых спецификаций и явного решения владельца.

## Связанные документы

- [SYSTEM_ARCH_FULL.md](../SYSTEM_ARCH_FULL.md), [ARCHITECTURE_FLOWS.md](../ARCHITECTURE_FLOWS.md)
- [ae3lite.md](../04_BACKEND_CORE/ae3lite.md), [AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md](../04_BACKEND_CORE/AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md)
- [MQTT_NAMESPACE.md](../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md), [MQTT_SPEC_FULL.md](../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md)
- [DATA_MODEL_REFERENCE.md](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md), [ZONES_AND_PRESETS.md](../06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md)
- [AGRONOMY_CRIMEA.md](../14_GROWING_REFERENCE/AGRONOMY_CRIMEA.md), [HARDWARE_BOM.md](../14_GROWING_REFERENCE/HARDWARE_BOM.md)
- [SINGLE_INSTANCE_SPOF_RUNBOOK.md](../08_SECURITY_AND_OPS/SINGLE_INSTANCE_SPOF_RUNBOOK.md)

---

## 1. Цель

Дать поэтапный план, как из одной сезонной теплицы 20 м² с капельным поливом выйти на
повторяемый модуль 400 м² и затем на N одинаковых модулей, не ломая защищённые пайплайны
(`ESP32 -> MQTT -> history-logger -> PostgreSQL -> Laravel -> Vue` и
`Laravel scheduler -> AE3 -> history-logger -> MQTT -> ESP32`), с бюджетным вариантом на
каждом шаге и с путём доведения NFT, DWC и прилива-отлива от пресета до рабочего контура.

## 2. Контекст: что есть в коде сейчас (сверено с `main` @ `ba461dc`, 2026-11-08)

| Факт | Где в коде | Проверено |
|------|-----------|-----------|
| AE3 знает только пакеты `two_tank`, `two_tank_drip_substrate_trays`, `single_tank`, `generic_cycle_start`, `lighting_tick` | `backend/services/automation-engine/ae3lite/application/services/workflow_topology.py` (`_PACKS`) | код |
| Laravel по умолчанию шлёт topology `two_tank_drip_substrate_trays` | `backend/laravel/app/Services/ZoneAutomationIntentService.php::resolveAe3TopologyForZone` | код |
| `irrigation_system_type` в AE3 читается и прокидывается, но не меняет граф стадий | `ae3lite/infrastructure/read_models/effective_targets_sql_utils.py` (поиск по `system_type`) | grep, без ветвления |
| Три разных перечня типов систем: пресеты `drip_tape|drip_emitter|ebb_flow|nft|dwc|aeroponics`, цикл `drip|substrate_trays|nft`, системные defaults `drip|substrate_trays|nft` | `StoreZoneAutomationPresetRequest.php`, `GrowCycleController.php`, `SystemAutomationSettingsCatalog.php` | код |
| Фронт сводит `dwc`, `ebb_flow`, `aeroponics` к `substrate_trays`, `nft` к `nft` | `backend/laravel/resources/js/composables/recipeSystemType.ts::normalizeIrrigationSystem` | код |
| Пресеты DWC/NFT — это та же капельная семантика «интервал + длительность полива» | `database/migrations/2026_04_17_120000_create_zone_automation_presets_table.php`, `..._130000_add_safe_aggressive_presets_for_drip_nft.php` | код |
| Нода держит одну зону (`nodes.zone_id`); общего узла раствора на несколько зон нет | `app/Models/DeviceNode.php`, AE3 single-writer per zone | код |
| Link-loss fail-safe на ноде: по умолчанию 30 с, глушит **все** насосы и реле | `firmware/nodes/common/components/node_framework/node_link_loss_failsafe.c` | код |
| Иерархия: `greenhouses` (тип `indoor|greenhouse|outdoor`) → `zones` → `nodes` → `node_channels`; уровня «площадка/модуль» нет | `database/migrations/2026_02_07_100000_create_greenhouse_types_table.php`, модели | код |
| Климат: greenhouse-level tick в AE3 есть, правила «вентилятор по температуре» нет | `ae3lite/api/greenhouse_climate_compat.py`, [HARDWARE_BOM.md](../14_GROWING_REFERENCE/HARDWARE_BOM.md) | код + док |
| `light_node` — только сенсор; PWM/WS2811 актуатор не реализован | [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) | док |

Вывод: рабочая сегодня — только капля на субстрате (`two_tank_drip_substrate_trays` /
`single_tank`). NFT, DWC и прилив-отлив существуют как ярлык пресета, и система
молча исполняет их как каплю.

## 3. Требования

1. Агрономия: листовая зелень и клубника нейтрального дня; коридоры — из
   [AGRONOMY_CRIMEA.md](../14_GROWING_REFERENCE/AGRONOMY_CRIMEA.md).
2. Масштаб: 20 м² (стенд) → 400 м² (модуль) → N × 400 м² (повтор без переписывания кода).
3. Типы гидропоники: капля (первая), затем прилив-отлив, NFT, DWC. Аэропоника — вне скоупа.
4. Среды: закрытый грунт (только лампы), теплица с досветкой, открытый грунт.
5. Крым, сезон март–ноябрь; декабрь–февраль теплица стоит; летний перегрев — главный риск.
6. Бюджет не определён → на каждом этапе бюджетный минимум и путь усиления.
7. Ограничения репозитория (AGENTS.md): без новых Python-сервисов; новые AE3 `task_type` и
   authority document types — только по явному решению владельца; MQTT-публикация только через
   history-logger; изменения БД только миграциями Laravel.

## 4. Архитектура / Дизайн

### 4.1. Модель данных: целевая форма (planned)

| Сущность | Сейчас | Нужно | Зачем |
|----------|--------|-------|-------|
| Площадка (`site`) | нет; `hydro/site/wx/...` зарезервирован в MQTT | `sites` (timezone, координаты, общая метеостанция) над `greenhouses` | N модулей в одной локации, общий метеодатчик, общий сервер |
| Модуль | нет | Шаблон модуля = `greenhouse` + набор зон + `infrastructure_instances`, клонируемый одной операцией | повторяемость 400 м² |
| Среда | `greenhouse_types`: `indoor|greenhouse|outdoor` | оставить; добавить в bundle флаги `has_supplemental_light`, `has_heating`, `rain_exposed` | разные цели климата/света по средам |
| Тип гидропоники | три несовпадающих enum | один канонический enum `hydro_system` (`drip`, `ebb_flow`, `nft`, `dwc`) + маппинг legacy-значений миграцией | убрать молчаливую подмену |
| Узел раствора на несколько зон | нет (нода = одна зона) | «zone group / solution loop»: одна зона-источник (баки, pH, EC) и K поливных зон-потребителей; lease на бак отдельно от lease зоны | модуль 400 м² = 1 узел раствора + 4 зоны полива |
| Политика fail-safe канала | один режим: link-loss гасит всё | `failsafe_state` на канал в NodeConfig: `off` / `hold` / `on` (аэрация DWC, циркуляция NFT, вытяжка летом) | выключение аэрации или вентиляции опаснее, чем их работа |

Решение о «zone group» — архитектурное (затрагивает AE3 single-writer, lease и NodeConfig);
до него модуль 400 м² собирается как 4 независимые зоны, каждая со своим поливным узлом и
**общими баками на одном узле раствора, управляемом вручную или одной «зоной-баком»**
(см. §6.2).

### 4.2. AE3: что нужно для каждого типа гидропоники

Общий принцип: тип системы = отдельный topology pack (граф стадий) в существующем реестре
`TopologyRegistry`, без нового `task_type`, если удаётся уложиться в существующие ingress
(`start-irrigation`, `start-solution-topup`, `start-cycle`). Где не удаётся — помечено.

| Тип | Гидравлика | Стадии AE3 (сверх общих startup/fill/correction) | Новые/изменённые команды и каналы | Требует решения владельца |
|-----|-----------|----------------------------------------------------|-----------------------------------|---------------------------|
| Капля (есть) | бак → насос → клапан → капельницы, дренаж в бак | есть | есть | — |
| Прилив-отлив | бак → насос → стол (fill) → hold → слив самотёком/клапаном (drain) | `flood_fill_start/check` (по поплавку стола или таймауту), `flood_hold`, `flood_drain_start/check` | поплавок/датчик уровня стола, `valve_drain` (на поливной ноде его нет), обратный клапан | новый pack `ebb_flow`; event `level_switch_changed` уже есть в контракте |
| NFT | непрерывная циркуляция бак → лотки → бак | `circulation_start` + длительный `circulation_monitor` (flow/level), без «полива по интервалу» | датчик протока (pulse counter), режим насоса `continuous` с heartbeat-продлением вместо `max_duration_ms` | новый pack `nft`; режим «длительного удержания» насоса — изменение command-контракта |
| DWC | бак = корневая зона; аэрация 24/7, долив, коррекция | `aeration_ensure_on`, `solution_topup` (есть), коррекция без полива; нет стадий irrigation | реле воздушного компрессора с `failsafe_state=on`, датчик растворённого O₂ (опционально), температура раствора | новый pack `dwc`; failsafe-политика канала — изменение NodeConfig |

Отдельно:
- **Порог температуры раствора** (DWC/NFT критичнее капли): канал `solution_temp_c` в `ph_node`
  сейчас не исполняется ([HARDWARE_BOM.md](../14_GROWING_REFERENCE/HARDWARE_BOM.md)) — нужен до DWC.
- **Решение полива по свету/дренажу** для клубники — позже; сейчас стратегия `task` (по расписанию).

### 4.3. MQTT-контракты

Базовые топики не меняются (`hydro/{gh}/{zone}/{node}/{channel}/{message_type}`). Нужно:

1. Канонический список каналов для новых ролей (`valve_drain`, `pump_circulation`,
   `air_pump`, `flow_*`, `level_table_*`) в
   [NODE_CHANNELS_REFERENCE.md](../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md).
2. Расширение NodeConfig: `failsafe_state` на канал; режим `continuous` с keepalive для насосов.
3. JSON Schema для сообщений, у которых её нет в `backend/services/common/schemas`
   (сейчас есть command, command_response, telemetry, status, heartbeat, error):
   `event`, `config_report`, `node_hello`, NodeConfig, `time/response`.
4. Для N модулей: `gh` — uid модуля; `hydro/site/...` — общие датчики площадки.
5. Безопасность (обязательна до 400 м²): TLS 8883, учётка на узел вместо общей `esp32_node`,
   отдельный wrap-ключ секрета на узел, plaintext 1883 выключен в prod.

### 4.4. Железо и ноды

| Роль | Прошивка | Что доделать |
|------|----------|--------------|
| Поливная зона (капля) | `storage_irrigation_node` | урезанный профиль «насос + клапан» для зон-потребителей 400 м² |
| Прилив-отлив | `storage_irrigation_node` или `pump_node` + `relay_node` | `valve_drain`, поплавок стола, стадия drain в fw stage guards |
| NFT | `pump_node` | pulse-counter датчика протока, режим continuous + keepalive |
| DWC | `relay_node` (GPIO помечены TODO) | GPIO, `failsafe_state=on` для компрессора |
| pH / EC | `ph_node`, `ec_node` | DS18B20 `solution_temp_c`; GPIO E-STOP |
| Климат | `climate_node` | правило «вентилятор/обогреватель по температуре» в AE3 climate tick; второй SHT31 на 400 м² |
| Досветка | `light_node` | PWM/реле-актуатор (planned) или свет на `climate_node` `set_pwm`/реле |

## 5. Этапы

### Этап 0 (сейчас – февраль 2027): стабилизация капли на 20 м²

- Капля на субстрате, `two_tank_drip_substrate_trays` или `single_tank`.
- Минимум: защита MQTT (TLS + учётка на узел) — до размещения в теплице.
- Решение «вентилятор по температуре» и `solution_temp_c`.
- Рецепт «капля, Крым, сезон» отдельной ревизией (см. AGRONOMY_CRIMEA).
- Выход: один полный сезонный цикл салата и клубники без ручного вмешательства в AE3,
  realhw-тесты `test_node` на fail-safe/link-loss зелёные.

### Этап 1 (март–май 2027): типы систем на стенде 20 м²

- Единый enum `hydro_system` + миграция legacy-значений; фронт перестаёт подменять тип,
  неподдерживаемый тип блокирует старт цикла с понятной ошибкой.
- Прилив-отлив первым (ближе всего к капле: тот же бак и насос, + стол и drain).
- Затем DWC (1–2 бака, аэрация, долив, температура раствора).
- NFT последним (нужен режим continuous и датчик протока).
- На каждом типе: pack в AE3, NodeConfig-каналы, fail-safe, node-sim сценарий, e2e, realhw.

### Этап 2 (лето–осень 2027): первый модуль 400 м²

- Модель «площадка → модуль → зоны»; клонирование модуля шаблоном.
- 1 узел раствора (баки 500–1000 л, pH, EC) + 4 поливные зоны по ~100 м².
- До решения «zone group» — зоны независимы, баки общие физически, а в софте
  ведёт одна зона-бак; зоны-потребители только открывают свой клапан
  (без собственной коррекции).
- Климат: 2 `climate_node`, 4–6 вытяжек, экран; шмели для клубники.
- Наблюдаемость: профиль `obs` обязателен, алерты на offline/stale, ежедневный backup.

### Этап 3 (2028+): N модулей

- Один сервер на площадку; брокер, PostgreSQL, бэкап — общие.
- AE3 остаётся single-writer per zone; при росте зон — проверить параллелизм worker'а и
  нагрузку на `commands`/`telemetry_samples` (нагрузочный тест на 4·N зон).
- Отдельная сеть Wi-Fi/VLAN узлов на модуль; при плохом Wi-Fi — проводной Ethernet (ESP32 + LAN8720) для узла раствора.
- Повтор модуля = шаблон БД + комплект BOM + одинаковые NodeConfig; без правки кода.

## 6. Бюджетный вариант

### 6.1. Ориентиры (EUR, розница ЕС, без доставки; детально — HARDWARE_BOM)

| Этап | Минимум | Комментарий |
|------|---------|-------------|
| 20 м² капля | 1 300–1 600 | узлы полива/pH/EC у владельца уже есть; сервер — существующий ПК |
| + прилив-отлив на 20 м² | +150–300 | стол/лотки, `valve_drain`, поплавок стола |
| + DWC на 20 м² | +150–250 | бак-ванна, компрессор, распылители, DS18B20 |
| + NFT на 20 м² | +250–450 | профили NFT, датчик протока, обратная магистраль |
| Модуль 400 м² (электроника и климат-обвязка) | 3 000–6 000 | без субстрата и каркаса |
| Модуль 400 м² с субстратом | 6 000–12 000 | субстрат — главный расходник |

Числа для NFT/DWC/прилива — оценка этого плана, не из сметы поставщика.

### 6.2. Принципы экономии

- Начинать модуль 400 м² с капли: она уже рабочая; NFT/DWC — на части площади после стенда.
- Один узел раствора на модуль, не на зону.
- Ручной экран и ручной долив чистой воды (`single_tank`) допустимы на старте.
- Без CO₂, без квантового датчика и без ламп в основном сезоне.
- Никакого Kubernetes/HA для 1–3 модулей: docker compose + проверенный restore.

## 7. Сезонность Крыма и среды

| Среда | Сезон | Что включено | Особенности системы |
|-------|-------|--------------|---------------------|
| Сезонная теплица | март–ноябрь, пауза/затенение июль–август | капля, позже прилив-отлив | перегрев: вытяжка и экран важнее досветки; обогрев только ночи марта–апреля и октября–ноября |
| Теплица с досветкой | февраль–ноябрь | + `light_node`-актуатор или свет на контакторе | нужен DLI/PPFD-датчик (не люкс); фотопериод в рецепте |
| Закрытый грунт | круглый год | DWC/NFT логичнее всего здесь | свет и VPD — актуаторы; холодный раствор летом важен |
| Открытый грунт | май–сентябрь | только капля, без возврата дренажа | дождь меняет водный баланс; pH/EC бака к грядке не прикладываются; нужен датчик осадков/влажности почвы — отдельный pack, не в первой волне |

Межсезонье (декабрь–февраль): консервация узлов (слив, промывка, хранение pH-электродов
в KCl), `control_mode=manual`, архивация циклов; весной — калибровка pH/EC перед стартом.

## 8. Тестирование

- Unit/интеграция AE3 на каждый новый pack (граф стадий, fail-safe, timeout).
- `node-sim` сценарии: потеря связи посреди fill/flood/circulation, залипший поплавок.
- Protocol contract tests на новые каналы и схемы (workflow `protocol-check.yml`).
- Realhw на `test_node` ([REALHW_TEST_NODE_AGENT_GUIDE.md](../13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md)):
  link-loss, E-STOP, failsafe_state для аэрации/циркуляции.
- Нагрузочный прогон на 4·N зон перед каждым новым модулем.

## 9. Ограничения и риски

| Риск | Влияние | Мера |
|------|---------|------|
| Молчаливая подмена типа системы (DWC/NFT исполняются как капля) | гибель растений при «включённом» DWC | блокировать старт цикла для неподдерживаемых типов (этап 1, первым делом) |
| Link-loss гасит аэрацию/циркуляцию через 30 с | DWC: кислородное голодание корней; NFT: пересыхание корней за минуты–часы | `failsafe_state` на канал |
| Общая MQTT-учётка узлов, plaintext 1883 по умолчанию в prod, общий wrap-ключ секретов | компрометация одного узла = управление всеми | TLS + учётка на узел + ключ на узел до этапа 2 |
| Один сервер = SPOF для всех модулей | остановка автоматики всех модулей | локальные fail-safe узлов, проверенный restore, UPS; HA не раньше 3+ модулей |
| Wi-Fi на 400 м² плёнки/поликарбоната | потери связи → link-loss циклы | отдельная точка доступа на модуль, Ethernet для узла раствора |
| Летний перегрев | потеря урожая клубники/салата | климатическое правило вентиляторов, экран, плановая пауза |
| Общий бак на 4 зоны без «zone group» | гонки коррекции между зонами | одна зона-бак ведёт коррекцию, остальные — только клапаны |

## 10. Задачи по ботам

| # | Задача | Исполнитель |
|---|--------|-------------|
| 1 | Решение: канонический enum `hydro_system`, «zone group / solution loop», `failsafe_state` канала, уровень `site` — ADR-набор | архитектор |
| 2 | Единый enum + миграция legacy-значений; запрет старта цикла с неподдерживаемым типом; модели `sites`/шаблон модуля | Hydro2 Бэк (Laravel) |
| 3 | Pack `ebb_flow` в `TopologyRegistry` + тесты; затем `dwc`, `nft` | Hydro2 Автоматика (AE3) |
| 4 | Правило климата «вентилятор/обогреватель по температуре» в greenhouse climate tick | Hydro2 Автоматика (AE3) |
| 5 | JSON Schema для `event`, `config_report`, `node_hello`, NodeConfig, `time/response` + parity-check | Hydro2 Автоматика (history-logger) + архитектор |
| 6 | MQTT TLS, учётка на узел, ключ обёртки секрета на узел, `MQTT_PLAINTEXT_ENABLED=0` по умолчанию в prod | архитектор + Hydro2 Автоматика (mqtt-bridge/HL); прошивка — вне ботов |
| 7 | UI: выбор типа системы без подмены, показ «не поддерживается», мастер клонирования модуля, экран «площадка → модули» | Hydro2 Фронт (Vue) |
| 8 | Прошивка: `failsafe_state`, continuous-режим насоса, `valve_drain`, датчик протока, `solution_temp_c`, GPIO `relay_node` | прошивка (владелец / отдельный исполнитель) |
| 9 | Нагрузочный тест AE3/HL на 16–40 зон и план индексов/retention | Hydro2 Автоматика + Hydro2 Бэк |

## 11. Планы развития

- После этапа 1 — обновить [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) и
  перенести реализованные решения в защищённые спецификации слоя.
- Ссылку на этот документ добавить в [01_SYSTEM/README.md](README.md) и [INDEX.md](../INDEX.md)
  отдельным изменением (в этом PR добавлен только новый файл).
