# ADR-0002. Группа зон на общем баке

**Версия:** 0.1
**Дата:** 2026-11-09
**Статус:** `proposed`
**Метки:** факты текущего кода — **live**; целевая модель — **planned**. Не контракт, пока статус не `accepted`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Целевая модель не меняет форму топика Protocol 2.0. Новый AE3 `task_type` и новый
authority document type не вводятся.

## Связанные документы

- [ADR-0001](ADR-0001-hydro-system.md) — у ресурса один `hydro_system`
- [ADR-0003](ADR-0003-failsafe-state.md) — аэрация и циркуляция живут на узле раствора
- [ADR-0004](ADR-0004-mqtt-prod-auth.md) — учётные данные этого узла такие же, как у остальных
- План масштаба: [PR #32](https://github.com/byYorick/hydro2.0/pull/32), §4.1 и §6.2 файла `doc_ai/01_SYSTEM/SCALING_PLAN_400M2_MODULES.md` (ветка `feature/docs-scaling-plan-400m2`)
- [EFFECTIVE_TARGETS_SPEC.md](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md), [ae3lite.md](../04_BACKEND_CORE/ae3lite.md)
- [MQTT_NAMESPACE.md](../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md), [GREENHOUSE_CLIMATE_CONTROL_SPEC.md](../06_DOMAIN_ZONES_RECIPES/GREENHOUSE_CLIMATE_CONTROL_SPEC.md) (DD-10, якорь `hydro/site/wx`)
- [DATA_MODEL_REFERENCE.md](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md)

## Контекст

Модуль 400 м² в PR #32 — один узел раствора на примерно четыре зоны полива.
Сейчас так собрать нельзя: коррекция и lease привязаны к одной зоне, нода
не состоит в нескольких зонах.

Сверено с `main` @ `ba461dce`.

### Нода и зона (**live**)

- `nodes.zone_id` — один nullable FK (`2025_11_16_000003_create_nodes_table.php:13`). Модель: `DeviceNode::zone()` (`DeviceNode.php:153`). Второй зоны у ноды нет.
- Уникальный индекс «одна нода на зону» снят (`2025_12_31_083648_drop_nodes_zone_unique_index.php`). В одной зоне много нод — нормальный случай (pH, EC, полив).
- Уточнение к обзору: «нода привязана ровно к одной зоне» — верно. «Общего бака нет» — верно как сущности химии. Реестр железа уже умеет владельца-теплицу: `infrastructure_instances.owner_type` = `zone` | `greenhouse` (`2025_12_25_151711_create_infrastructure_instances_table.php`). `channel_bindings` связывает канал ноды с экземпляром, канал принадлежит только одному экземпляру (`2025_12_25_151712_create_channel_bindings_table.php:28`). Готовность зоны видит ноды и своей `zone_id`, и привязок к greenhouse-asset (`ZoneReadinessService.php:1007–1028`). Это учёт оборудования и климата, не общий контур pH/EC и не общий lease.

### Lease (**live**)

- Зона: `ae_zone_leases` (PK `zone_id`, `owner`, `leased_until`, `updated_at`, плюс `claim_generation` и `process_run_id`). Репозиторий `ae3lite/infrastructure/repositories/zone_lease_repository.py`. Одна активная execution task на зону.
- history-logger отклоняет операторскую команду, пока lease зоны удерживается: `backend/services/history-logger/commands/lease_gate.py` (запрос к `ae_zone_leases` около строки 141).
- Климат теплицы — отдельная таблица `greenhouse_automation_leases` (`ae3lite/greenhouse_climate/run_tick.py`, `_claim_greenhouse_lease`). Это прецедент lease не на зону, но только для climate tick. На баки он не распространяется.

Команды по-прежнему идут Laravel → AE3 → history-logger → MQTT. Прямой publish из AE и Laravel запрещён.

### MQTT (**live**)

Топик: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`. Сегмент `{zone}` — uid зоны ноды. Менять порядок сегментов нельзя.

`hydro/site/wx/{node}/…` уже занят метеостанцией площадки: служебная теплица `uid=site` и зона `uid=wx` (`DATA_MODEL_REFERENCE.md` §2.1, `GREENHOUSE_CLIMATE_CONTROL_SPEC.md` DD-10). Это не узел раствора.

Уровня `sites` в схеме нет. Модуль как сущность не выделен: повторяемая единица в плане — теплица.

### Рецепты (**live**)

pH/EC target|min|max берутся только из активной фазы рецепта. `cycle.phase_overrides` и `zone.logic_profile` их не переопределяют. Две зоны с разными фазами — два независимых setpoint и два writer'а коррекции. Общего правила «один бак — одна химия» нет.

## Решение

### 1. Ресурс раствора

Новая таблица `solution_resources` (имя в миграции зафиксировать так; в тексте допустим синоним «узел раствора»):

| Колонка | Смысл |
|---|---|
| `id`, `uid` | суррогат и стабильный uid |
| `greenhouse_id` | модуль, к которому относится бак |
| `hydro_system` | один канон из ADR-0001 на весь бак |
| `source_zone_id` | зона, к которой привязана нода раствора (`nodes.zone_id`) |
| `correction_zone_id` | та же source-зона; только она ведёт pH/EC |

Связь зон: `solution_resource_zones` (`solution_resource_id`, `zone_id` UNIQUE, `role` = `source` | `consumer`). У ресурса ровно одна `source`. Зона входит не больше чем в один ресурс. Нода по-прежнему имеет один `zone_id`: нода баков, pH и EC стоит на source-зоне; клапан потребителя — на своей зоне.

Баки и насосы не дублируются новой таблицей оборудования. Экземпляры остаются в `infrastructure_instances`. На общий контур вешается nullable `solution_resource_id`. Для модуля с одним баком владелец экземпляра может остаться `greenhouse`; FK нужен, когда в одной теплице два независимых бака. `channel_bindings` не меняет смысл.

Это не новый authority document type. Коррекция читает существующие документы source-зоны и compiled bundle этой зоны.

### 2. Кто ведёт коррекцию

Единственный writer pH/EC — source-зона. Её активная фаза — единственный setpoint (`EFFECTIVE_TARGETS_SPEC` не ослабляется).

Зона-потребитель не включает подсистему correction. Если включает — старт её цикла и старт коррекции source отклоняются с `solution_consumer_correction_forbidden` (код добавить в `error_codes.json` в PR реализации).

Полив потребителя открывает только свой клапан и, пока действует сериализация из §3, просит source включить общий насос. Дозу потребителя с чужого узла pH/EC не считают.

### 3. Lease и сериализация команд

Новая таблица `ae_solution_resource_leases` той же формы, что `ae_zone_leases`: PK `solution_resource_id`, `owner`, `leased_until`, `updated_at`, `claim_generation`, `process_run_id`.

Правило v1 — последовательный полив, не параллельные клапаны:

- Задача остаётся зональной (существующие `start-irrigation` / коррекция / topup). Новый `task_type` не заводится.
- Перед командой на общий насос, клапан бака или дозатор задача берёт lease ресурса и lease своей зоны.
- Вторая зона, пока lease ресурса занят, получает `solution_resource_busy` (аналог `start_cycle_zone_busy`) и не создаёт вторую dosing-задачу.
- history-logger в `lease_gate.py` отклоняет команду на канал, привязанный к ресурсу, если lease ресурса держит не этот source. Зональный gate не снимается: клапан потребителя по-прежнему закрыт чужим lease его зоны.

Параллельные клапаны при постоянно крутящемся насосе — следующая ревизия, отдельный ADR. В v1 её нет: текущая команда `run_pump` с `duration_ms` не умеет «сессию насоса на несколько зон».

Климатный `greenhouse_automation_leases` не переиспользуется под бак.

### 4. Разные рецепты на одном баке

Сравнение setpoint — target pH и target EC активных фаз source и каждого потребителя, у которого цикл запущен. Совпадение после округления pH до 0.01 и EC до 0.01 — можно поливать. Иначе `solution_target_conflict`, без среднего и без «взять более строгий».

Потребитель без собственного цикла может открывать клапан только с явным `targets_follow_resource=true` на строке `solution_resource_zones`. Тогда химия берётся из source, фаза потребителя setpoint не задаёт.

Разные культуры с разным EC на одном баке система не исполняет. Это отказ конфигурации, не усреднение.

### 5. MQTT без смены Protocol 2.0

Форма топика не меняется. Нода раствора публикует в `hydro/{gh}/{zone}/{node}/…`, где `{zone}` — uid source-зоны. Отдельного сегмента `solution` нет. `hydro/site/wx/…` не занимается баком.

Команда потребителя на свой клапан идёт в топик ноды потребителя. Команда на насос бака и дозатор — в топик ноды source. Связь «этот клапан кормится из того бака» живёт в БД, не в топике.

Версионированный namespace понадобится только если нода должна существовать вне всякой зоны. Это не требование модуля 400 м² и этим ADR не вводится.

### 6. Площадка и модуль

В том же изменении схемы, отдельным ADR не дробить:

| Сущность | Решение |
|---|---|
| Площадка | таблица `sites` (имя, timezone, широта, долгота). `greenhouses.site_id` nullable FK |
| Модуль | это `greenhouse`, не новая таблица `modules`. Клон модуля — операция Laravel: теплица, зоны, один `solution_resource`, набор `infrastructure_instances` |
| N модулей | несколько `greenhouses` одного `site`, один брокер, один PostgreSQL. AE3 остаётся single-writer на зону плюс lease ресурса |
| Погода | как сейчас: якорь `uid=site` / `wx` и `shared_weather_station_node_id`. На `sites` переносится не раньше отдельной правки DD-10 |

До миграции допустим эксплуатационный мост из PR #32 §6.2: четыре независимые зоны, физически общий бак, в софте коррекция только у одной зоны, остальные без коррекции. Это не схема `solution_resources` и не считается выполнением ADR. Мост не получает lease ресурса, гонка двух зон на одном баке при нём остаётся.

## Альтернативы

- Считать greenhouse-owned `infrastructure_instances` уже готовым общим баком. Отклонено: нет единственного writer химии и нет lease на дозу. Готовность зоны лишь видит чужую ноду.
- Делать source-зону единственной зоной модуля, а «зоны полива» — каналами. Отклонено: ломает рецепт, расписание и UI «зона = культура», ради которых модуль и делится на четыре.
- Новый `task_type=solution_correction`. Отклонено: запрет на новые task_type без явного запроса; хватает lease поверх текущих ingress.
- Топик `hydro/{gh}/solution/{uid}/…`. Отклонено: ломает порядок сегментов Protocol 2.0.
- Параллельные клапаны в первой версии. Отклонено: нет контракта общей сессии насоса.
- Усреднять pH/EC четырёх рецептов. Отклонено: для зелени и клубники это неверный раствор, не компромисс.

## Последствия

- Пока ADR `proposed`, схема и lease не меняются (**live** — зона и нода как сейчас).
- После принятия модуль 400 м² описывается одним ресурсом и четырьмя зонами-потребителями. Четыре независимых бака остаются возможными: зона просто не входит в `solution_resource_zones`.
- history-logger остаётся единственной точкой MQTT-publish. Появляется второй gate (lease ресурса) рядом с зональным.
- Нагрузка: последовательный полив четырёх зон удлиняет окно, не увеличивает параллельные dosing-задачи. Это осознанный обмен.
- Клонирование модуля не копирует `node_secret`, MQTT-пароли и lease.
- Контракты `MQTT_NAMESPACE.md` и `DATA_MODEL_REFERENCE.md` обновляются в PR реализации, когда таблицы появятся. Этот файл их не подменяет.

## Задачи

| # | Задача | Исполнитель |
|---|---|---|
| 1 | Миграции `sites`, `greenhouses.site_id`, `solution_resources`, `solution_resource_zones`, `ae_solution_resource_leases`, nullable `infrastructure_instances.solution_resource_id` | Hydro2 БД |
| 2 | Модели, Form Request, операция клонирования модуля, отказ старта при чужой коррекции потребителя и при конфликте target | Hydro2 Бэк |
| 3 | Захват и продление lease ресурса в существующих ingress; код `solution_resource_busy`; без нового `task_type` | Hydro2 Автоматика |
| 4 | `lease_gate.py`: отказ команды на канал ресурса при чужом lease; тест рядом с текущим зональным gate | Hydro2 Автоматика |
| 5 | Экран «бак → зоны», конфликт целевых pH/EC, клон модуля. Не смешивать с scheduler cockpit | Hydro2 Фронт |
| 6 | Нода раствора остаётся обычной нодой source-зоны. Отдельной прошивки «мультизона» нет | прошивка — без задачи в этом ADR |

## Критерии приёмки

1. Две зоны одного ресурса не дозируют параллельно: вторая получает `solution_resource_busy`, в `ae_solution_resource_leases` один owner.
2. Потребитель с включённой коррекцией не стартует (`solution_consumer_correction_forbidden`). Source с `hydro_system=drip` дозирует как сегодняшняя зона.
3. Фазы с pH target 5.80 и 6.10 на одном ресурсе дают `solution_target_conflict`. Фазы 5.80 и 5.80 проходят проверку.
4. Топик ноды раствора после привязки имеет вид `hydro/{gh_uid}/{source_zone_uid}/{node_uid}/…`. Сегмент `solution` и перенос в `hydro/site/wx` отсутствуют. Контрактный тест namespace это фиксирует.
5. Операторская `dose` на канал ресурса при удержанном lease отклоняется history-logger так же явно, как сегодня отклоняется команда при `ae_zone_leases`.
6. Клон модуля создаёт новую теплицу, зоны и пустой ресурс без копирования `nodes` и секретов.
7. Зона вне ресурса ведёт себя как сейчас: только `ae_zone_leases`, свой pH/EC.
