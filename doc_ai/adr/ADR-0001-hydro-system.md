# ADR-0001. Единый перечень `hydro_system`

**Версия:** 0.1
**Дата:** 2026-11-09
**Статус:** `proposed`
**Метки:** факты текущего кода — **live**; целевое поведение — **planned**. Не контракт, пока статус не `accepted`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Документ не меняет протокол. Смена enum и отказ старта цикла потребуют отдельного PR
в валидацию, AE3 и каталог ошибок.

## Связанные документы

- [ADR-0002](ADR-0002-solution-resource.md) — общий бак не подменяет тип системы
- [ADR-0003](ADR-0003-failsafe-state.md) — дефолты канала зависят от `hydro_system`
- План масштаба: [PR #32](https://github.com/byYorick/hydro2.0/pull/32), файл `doc_ai/01_SYSTEM/SCALING_PLAN_400M2_MODULES.md` в ветке `feature/docs-scaling-plan-400m2` (в `main` @ `ba461dce` файла нет)
- [ZONES_AND_PRESETS.md](../06_DOMAIN_ZONES_RECIPES/ZONES_AND_PRESETS.md), [EFFECTIVE_TARGETS_SPEC.md](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md)
- [ae3lite.md](../04_BACKEND_CORE/ae3lite.md), [ERROR_CODE_CATALOG.md](../04_BACKEND_CORE/ERROR_CODE_CATALOG.md)
- [DATA_MODEL_REFERENCE.md](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md) §2.1.1 `greenhouse_types`
- [AGRONOMY_CRIMEA.md](../14_GROWING_REFERENCE/AGRONOMY_CRIMEA.md)

## Контекст

Культуры: листовая зелень и клубника, Крым, сезонные теплицы. Масштаб из PR #32:
20 м² → модуль 400 м² → N модулей. Рабочий контур сегодня — капля. NFT, DWC и
прилив-отлив записаны как ярлыки и исполняются гидравликой капли.

Сверено с `main` @ `ba461dce`. Ниже — факт, не пересказ обзора.

### Три словаря (**live**)

| Место | Допустимые значения | Файл |
|---|---|---|
| Пресет зоны | `drip_tape`, `drip_emitter`, `ebb_flow`, `nft`, `dwc`, `aeroponics` | `backend/laravel/app/Http/Requests/StoreZoneAutomationPresetRequest.php:26`, то же в `UpdateZoneAutomationPresetRequest.php` и `SubstrateRequest.php` |
| Колонка пресета по умолчанию | `dwc` | `backend/laravel/database/migrations/2026_04_17_120000_create_zone_automation_presets_table.php:22`; запись без поля тоже `dwc` — `ZoneAutomationPresetService.php:46` |
| Создание цикла | `drip`, `substrate_trays`, `nft` | `GrowCycleController.php:405` |
| Дефолт цикла, если поле пустое | `drip` | `GrowCycleCreator.php:67` |
| Системные defaults | `drip`, `substrate_trays`, `nft`; пример значения `drip` | `SystemAutomationSettingsCatalog.php:270`, проверка на строке 590 |
| Фаза рецепта в UI | `drip_tape`, `drip_emitter`, `nft`, `dwc`, `ebb_flow`, `aeroponics` | `backend/laravel/resources/js/Components/RecipeEditor.vue` (options около строк 288–305) |

Фронт схлопывает ярлыки в три значения цикла (**live**):

- `drip` / `drip_tape` / `drip_emitter` → `drip`
- `substrate` / `substrate_trays` / `ebb_flow` / `dwc` / `aeroponics` → `substrate_trays`
- `recirc` / `nft` → `nft`

Файл: `backend/laravel/resources/js/composables/recipeSystemType.ts`, функция `normalizeIrrigationSystem` (строки 11–32). Тот же схлоп в фильтре пресетов: `PresetSelector.vue:110–111` (`substrate_trays` = `dwc` + `ebb_flow` + `aeroponics`).

### Что реально исполняет AE3 (**live**)

`TopologyRegistry._PACKS` (`workflow_topology.py:501–507`) содержит пять пакетов, не три:

| pack id | Граф | Зачем |
|---|---|---|
| `two_tank` | `TWO_TANK` | гидравлика, `irrigation_binding="generic"` |
| `two_tank_drip_substrate_trays` | тот же объект `TWO_TANK` | гидравлика, `irrigation_binding="drip_substrate_trays"` |
| `single_tank` | `TWO_TANK` без стадий `clean_fill_*` | гидравлика одного бака |
| `generic_cycle_start` | одна стадия `startup` | diagnostics, не тип гидропоники |
| `lighting_tick` | стадия `apply` | свет, не тип гидропоники |

Уточнение к обзору: «AE3 знает только три пакета» — неточно. Гидравлических графа два (`TWO_TANK` и `SINGLE_TANK`). `two_tank` и `two_tank_drip_substrate_trays` делят один граф (`topology_pack.py:20–21`). Поле `irrigation_binding` нигде не читается, кроме сборки пакета и unit-теста `test_ae3lite_topology_pack.py`. Отдельных пакетов `nft`, `dwc`, `ebb_flow` нет.

`irrigation_system_type` фазы копируется в effective targets (`effective_targets_sql_utils.py:145–147` и `:261`) и в схему коррекции как необязательная строка (`zone_correction.py:422`). Ветки «если nft / dwc — другой граф» нет.

### Откуда берётся topology intent (**live**)

`ZoneAutomationIntentService::resolveAe3TopologyForZone` (`ZoneAutomationIntentService.php:20–36`) читает `subsystems.diagnostics.execution.topology` активного logic profile. Непустая строка возвращается как есть, без сверки с `_PACKS` и без чтения пресета. Если поля нет или чтение бросило исключение — возвращается `two_tank_drip_substrate_trays`.

Уточнение к обзору: Laravel не «всегда подставляет каплю». Подставляет капельный pack, когда topology в профиле пустая. Пресет с `irrigation_system_type=dwc` в этот метод не передаётся. Итог тот же, что в обзоре: DWC/NFT/прилив, выбранные в пресете или схлопнутые фронтом в `substrate_trays`, не меняют граф стадий. Неизвестная topology упадёт позже в `TopologyRegistry.pack` (`KeyError`), а не на границе старта с понятным кодом.

Пресеты DWC/NFT в сидах — те же поля «интервал + длительность», что и капля (`2026_04_17_120000_create_zone_automation_presets_table.php`, `2026_04_17_130000_add_safe_aggressive_presets_for_drip_nft.php`).

### Среда теплицы (**live**)

`greenhouse_types.code`: `indoor`, `greenhouse`, `outdoor` (`database/migrations/2026_02_07_100000_create_greenhouse_types_table.php`, справочник в `DATA_MODEL_REFERENCE.md` §2.1.1). На выбор графа AE3 не влияет. Уровень «площадка» — в ADR-0002.

Аэропоника есть в пресетах и во фронте. PR #32 выводит её из скоупа масштабирования.

## Решение

### 1. Канонический перечень

Закрытый enum `hydro_system`:

| Значение | Смысл | Pack AE3 сейчас |
|---|---|---|
| `drip` | капля на субстрате (лента и эмиттер — не разные системы) | **live**: один из `two_tank`, `two_tank_drip_substrate_trays`, `single_tank` |
| `ebb_flow` | прилив-отлив | **planned**, pack нет |
| `nft` | NFT, постоянная циркуляция | **planned**, pack нет |
| `dwc` | DWC, раствор — корневая зона, аэрация | **planned**, pack нет |

`aeroponics` в перечень не входит (вне скоупа PR #32). Новые значения только новым ADR.

Ось баков не входит в enum. `tanks_count` / наличие чистого бака по-прежнему выбирает `single_tank` или двухбаковый pack. Для `drip` это существующие три id. `generic_cycle_start` и `lighting_tick` остаются topology задачи, их нельзя записать в `hydro_system`.

Источник истины значений — PHP enum `App\Enums\HydroSystem` (Laravel владеет схемой и валидацией). Рядом, в том же enum, два признака на значение:

- `implemented` — есть ли зарегистрированный граф в `TopologyRegistry`;
- совместимость со средой `indoor` / `greenhouse` / `outdoor` (таблица ниже).

Снимок для паритета — один JSON `backend/services/common/schemas/hydro_system.enum.json` (значения, `implemented`, матрица сред). Его правят только вместе с enum. Python-frozenset `ae3lite/domain/hydro_system.py` и TypeScript `backend/laravel/resources/js/domain/hydroSystem.ts` не ведут собственный список: тесты сравнивают их с JSON. Расхождение — падение CI (PHPUnit, pytest AE3, Vitest), не warning.

Лента и эмиттер не становятся вторым enum. Если UI хочет различать их, это необязательное поле доставки `tape` / `emitter` на фазе или пресете. AE3 по нему не ветвится. `substrate_type` остаётся типом субстрата.

### 2. Где лежит значение

Одно имя поля `hydro_system` в четырёх местах (миграция Laravel, не ручной DDL):

| Место | Роль |
|---|---|
| `zones.hydro_system` | чем зона собрана аппаратно |
| `grow_cycle_phases.hydro_system` | чем фаза рецепта хочет поливаться |
| `zone_automation_presets.hydro_system` | вместо `irrigation_system_type` после миграции данных |
| `grow_cycles.settings.irrigation.system_type` и `automation_defaults.water_system_type` | те же четыре строки, не отдельный словарь |

Старые колонки на время миграции читаются через таблицу алиасов ниже. После backfill писатели отдают только канон. Химические target pH/EC по-прежнему только из активной фазы рецепта (`EFFECTIVE_TARGETS_SPEC`): `hydro_system` не подменяет setpoint.

### 3. Алиасы и миграция

| Старое значение | Куда |
|---|---|
| `drip`, `drip_tape`, `drip_emitter` | `drip` |
| `nft`, `recirc` | `nft` |
| `ebb_flow` | `ebb_flow` |
| `dwc` | `dwc` |
| `aeroponics` | не канон; строка помечается `needs_review`, цикл не стартует |
| `substrate`, `substrate_trays` | не угадывать. Это корзина, куда фронт сложил и лотки, и DWC, и прилив, и аэропонику. `needs_review`, цикл не стартует, пока оператор не выберет канон |

Автоперевод `substrate_trays` → `drip` запрещён: он сохранил бы молчаливую подмену. Сиды пресетов с явным `dwc` / `nft` / `drip_tape` мигрируют по таблице, не по дефолту колонки.

### 4. Fail-closed

Цикл гидравлики не стартует, если для `hydro_system` нет реализованного графа.

Реализован сегодня только `drip`. Для него Laravel по-прежнему выбирает один из трёх существующих pack id по бакам, но только после проверки `implemented=true`. Пустая topology больше не означает `two_tank_drip_substrate_trays`, если у зоны `hydro_system` другой.

Отказ — до записи `zone_automation_intents`, стабильным `error_code` (кодов ещё нет в `backend/error_codes.json`, добавить в PR реализации):

| Код | Когда |
|---|---|
| `hydro_system_not_implemented` | значение канона есть, pack в реестре не помечен |
| `hydro_system_unknown` | строка вне enum |
| `hydro_system_needs_review` | легаси `substrate_trays` / `aeroponics` без выбора оператора |
| `hydro_system_environment_forbidden` | пара система×среда запрещена матрицей |

Тот же отказ на ingress AE3 (`start-cycle`, `start-irrigation`, `start-solution-topup`, `start-solution-change`), если intent всё же пришёл: повторная проверка, без подстановки капельного pack. Новый `task_type` не вводится.

Не блокируются этой проверкой: `lighting_tick`, diagnostics `generic_cycle_start` (он не открывает полив и не дозирует), greenhouse climate tick. Коррекция pH/EC для нереализованного типа не запускается: она часть гидравлического pack.

`ZoneLogicProfileNormalizer` сегодня узнаёт только `two_tank` и `two_tank_drip_substrate_trays` (`ZoneLogicProfileNormalizer.php:134` и `:254`). В PR реализации нормализатор не расширяют «любой строкой»: нереализованный `hydro_system` не записывается в `diagnostics.execution.topology`.

### 5. Среда

`greenhouse_types` не сливается с `hydro_system`. Матрица старта (**planned**):

| Среда | `drip` | `ebb_flow`, `nft`, `dwc` |
|---|---|---|
| `indoor` | да, когда pack есть | да, когда pack есть |
| `greenhouse` | да | да, когда pack есть |
| `outdoor` | да | нет (`hydro_system_environment_forbidden`), даже после появления pack |

Открытый грунт в PR #32 — капля без возврата дренажа в бак. NFT/DWC/прилив там не стартуют, пока отдельный ADR не разрешит. Сезон Крыма (вентиляция летом, пауза зимой) эту матрицу не сужает: это политика канала (ADR-0003) и климат, не запрет типа.

## Альтернативы

- Оставить три словаря и «документировать, что DWC значит каплю». Отклонено: оператор включает DWC и получает полив по таймеру.
- Считать источником истины фронтовый `normalizeIrrigationSystem`. Отклонено: функция как раз уничтожает DWC и прилив.
- Завести pack на каждый ярлык пресета сразу (`drip_tape` и `drip_emitter` отдельно). Отклонено: граф один, расхождение списков вернётся.
- Молча мапить `substrate_trays` → `drip`. Отклонено: часть таких циклов когда-то была DWC на экране рецепта.
- Разрешить старт нереализованного типа «в ручном режиме, но intent записать». Отклонено: intent без pack снова свалится в дефолт или в `KeyError` без кода для UI.

## Последствия

- Пока ADR `proposed`, runtime не меняется: капля остаётся единственным рабочим графом (**live**).
- После принятия первые же PR: enum, JSON-снимок, миграция с `needs_review`, отказ старта. Паки `ebb_flow` / `dwc` / `nft` — отдельные PR автоматики, каждый переключает `implemented` только вместе с тестом графа.
- `ERROR_CODE_CATALOG.md` и `backend/error_codes.json` обновляются в PR реализации, не этим файлом.
- Фронт перестаёт вызывать `normalizeIrrigationSystem` как подмену. Неподдержанный тип виден в UI до нажатия «старт».
- Аэропоника остаётся в старых строках БД до ручного разбора и пропадает из селектов.
- Совместимость протокола не затрагивается: MQTT payload команд не меняется.

## Задачи

| # | Задача | Исполнитель |
|---|---|---|
| 1 | Enum `HydroSystem`, колонки `hydro_system`, backfill по таблице алиасов, `needs_review` без автодогадки, валидация Form Request вместо трёх `Rule::in` | Hydro2 Бэк |
| 2 | Миграции колонок и сидов пресетов; старые строки `substrate_trays` / `aeroponics` не обновлять втихую | Hydro2 БД |
| 3 | Отказ гидравлического старта до intent и повтор на ingress AE3; не подставлять `two_tank_drip_substrate_trays`; коды в `error_codes.json` | Hydro2 Бэк и Hydro2 Автоматика |
| 4 | JSON-снимок, frozenset, TS-модуль, три теста паритета в CI | Hydro2 Бэк, Hydro2 Автоматика, Hydro2 Фронт |
| 5 | Селекты рецепта, пресета и цикла показывают четыре канонических значения; нереализованное — блокировка с кодом, без схлопывания в `substrate_trays` | Hydro2 Фронт |
| 6 | Pack `ebb_flow`, затем `dwc`, затем `nft` — отдельные изменения; `implemented=true` только с тестом графа | Hydro2 Автоматика |
| 7 | Прошивка под новые каналы этих pack — не в этом ADR | прошивка, когда pack принят |

Новый Python-сервис и новый AE3 `task_type` не требуются.

## Критерии приёмки

1. В репозитории один список значений. CI падает, если PHP enum, JSON, Python и TypeScript разошлись хотя бы на строку или флаг `implemented`.
2. Зона с `hydro_system=dwc` (и так же `nft`, `ebb_flow`) не получает intent `two_tank_drip_substrate_trays`. Ответ старта содержит `hydro_system_not_implemented`. В `zone_automation_intents` строки нет.
3. Зона с `hydro_system=drip` и двумя баками стартует существующим двухбаковым pack, как до смены словаря. Тест `ZoneAutomationStartIrrigationControllerTest` остаётся зелёным на этом пути.
4. Цикл, у которого в БД лежит `substrate_trays` или `aeroponics`, не стартует с `hydro_system_needs_review`, пока оператор не сохранит канон.
5. `outdoor` + `nft` отклоняется с `hydro_system_environment_forbidden` даже в тесте, где флаг `implemented` у `nft` принудительно включён.
6. `lighting_tick` зоны с `hydro_system=dwc` не отвергается правилом этого ADR.
7. В UI нет пути, который сохраняет `dwc` и показывает оператору `substrate_trays`.
