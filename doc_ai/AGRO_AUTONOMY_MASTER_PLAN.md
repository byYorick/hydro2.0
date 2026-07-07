# AGRO_AUTONOMY_MASTER_PLAN.md
# Мастер-план доведения hydro2.0 до автономной эксплуатации

**Дата:** 2026-07-07
**Версия:** 1.0
**Статус:** утверждён к работе (этапы A–F)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

> Этот план дополняет `AUDIT_2026_07_07_RELIABILITY_PLAN.md` (этапы R1–R7 остаются актуальными
> и включены сюда ссылками). Фокус текущего плана: **агрономические контуры автоматизации**,
> внешний алертинг и путь выхода на реальное железо для автономной работы теплицы.

---

## 1. Цель

Довести систему до состояния, в котором теплица с плодовыми культурами (томат, огурец,
клубника) работает автономно с визитами оператора **1–2 раза в неделю**, а все нештатные
ситуации доставляются оператору во внешний канал (Telegram) без необходимости смотреть в UI.

## 2. Контекст и целевой сценарий эксплуатации

Зафиксированные вводные (2026-07-07):

| Параметр | Значение |
|----------|----------|
| Текущая среда | Стенд / HIL (node_sim + test_node); реальное железо — позже |
| Культуры | Плодовые: томат, огурец, клубника (длинные циклы, большое водопотребление, фотопериод-чувствительность) |
| Тип объекта | Теплица с естественным светом; климат — крышные форточки (контур `greenhouse_climate_tick` уже реализован) |
| Зональный климат (T/RH/CO₂) | Полный исполняемый контур **не требуется** на этом этапе — достаточно мониторинга и форточек |
| Внешний алертинг | Telegram |
| Автономность | Визиты 1–2 раза в неделю |
| Приоритет работ | Сначала агрономические контуры, затем надёжность/прошивки |

Агрономические следствия для плодовых культур:

- **Фотопериод** обязан соблюдаться строго: томат при круглосуточной досветке получает
  хлороз/повреждение листа, клубника фотопериод-чувствительна. Гарантированный OFF — критичен.
- **Водопотребление** взрослого томата — до 2–3 л/день с растения: без автодолива бак
  опустеет между визитами оператора.
- **Температура раствора**: оптимум 18–22 °C; выше 26–28 °C падает растворённый кислород,
  растут корневые патогены, дрейфует pH/EC. Нужен хотя бы контроль + алерт, в идеале контур.
- **Деградация раствора**: за 1–2 недели накапливаются соли/патогены → плановая подмена.

## 3. Текущее состояние (краткая карта, 2026-07-07)

### Что уже работает (не переделываем)

| Контур | Статус | Ключевые файлы |
|--------|--------|----------------|
| Коррекция pH/EC (импульсный PID, fail-closed no-effect) | **Готово** | `ae3lite/application/handlers/correction.py`, `ae3lite/domain/services/correction_planner.py` |
| Two-tank startup (clean fill → solution fill → recirc → ready) | **Готово** | `ae3lite/application/services/workflow_topology.py`, `handlers/clean_fill.py` … |
| Полив (irrigation, guards, E-STOP, recovery) | **Готово** | `handlers/decision_gate.py`, `handlers/irrigation_check.py` |
| Климат теплицы (крышные форточки, rule-based V1) | **Готово** | `ae3lite/greenhouse_climate/decision_engine.py`, `GreenhouseClimateDispatchService.php` |
| Освещение — базовый dispatch `lighting_tick` | **Частично** | `ScheduleDispatcher.php`, `cycle_start_planner.py:_build_lighting_tick_plan` |
| Level switches (two-tank) | **Готово** | `ae3lite/application/level_monitor.py` |
| day/night конфиг для pH/EC/lighting в runtime | **Готово (инфраструктура)** | `ae3lite/config/runtime_plan_builder.py:_build_day_night_config` |

### Что отсутствует / незамкнуто (предмет этого плана)

| Пробел | Влияние на плодовые | Приоритет |
|--------|---------------------|-----------|
| Освещение шлёт статичный duty, нет гарантированного OFF | Нарушение фотопериода, ожог, перерасход энергии | **A (высший)** |
| Нет автодолива бака в фазе роста | Пустой бак между визитами, стоп полива | **B** |
| Нет контура/алертов t° раствора | Корневые гнили, дрейф pH/EC | **C** |
| Нет подмены раствора / CIP | Деградация раствора за 1–2 недели | **D** |
| Внешний алертинг (Telegram) отсутствует | Тихие ночные аварии | **E** |
| Firmware fail-safe при потере связи | Перелив/ожог при выходе на железо | **F (перед реальным железом)** |
| Reliability-хвост R3/R4 (незакоммичен) | Потеря телеметрии, застревание задач | **предусловие (см. §11)** |

---

## 4. Общий принцип реализации

1. **Doc-first**: каждый контур сначала фиксируется в спецификации `doc_ai/`, затем код.
2. **Только через history-logger**: ни Laravel, ни AE3 не публикуют команды в MQTT напрямую.
3. **Аддитивность и fail-closed**: новые поведения не ломают защищённый пайплайн; при неполной
   конфигурации — явная ошибка/безопасное состояние, а не «тихая» деградация.
4. **Каждый этап — независимый merge** с зелёными suites (`make test`, `make test-ae`, HL pytest,
   `protocol-check` при затрагивании контрактов).
5. **Source of truth targets** — активная фаза рецепта; zone override не переопределяет
   chemical setpoints (инвариант из `EFFECTIVE_TARGETS_SPEC.md`).

Карта этапов и зависимостей:

```
предусловие: R3/R4 reliability хвост (закоммитить, довести)
      │
      ▼
A (освещение day/night + OFF) ──► B (автодолив) ──► C (t° раствора) ──► D (подмена раствора/CIP)
      │
      └──► E (Telegram-алерты) — можно параллельно, независимо
                                  │
                                  ▼
                          F (firmware fail-safe) — перед выходом на реальное железо
```

---

## Этап A — Освещение: day/night duty + гарантированный OFF (ВЫСШИЙ ПРИОРИТЕТ)

### A.0 Проблема

Сейчас `lighting_tick` всегда шлёт одну команду включения с фиксированным `pwm_duty`
(default 100%, см. `cycle_start_planner.py:_resolve_lighting_pwm_duty` → fallback 100).
Orchestrator триггерит tick только на **границе** окна фотопериода
(`SchedulerCycleOrchestrator.php:509-511`, `$desiredNow !== $desiredLast`), но AE3 при этом
всегда строит план «включить» — **нет ветки выключения** на границе выхода из окна.

Итог: свет может остаться включённым после конца фотопериода; day/night dimming (яркость день/ночь)
не применяется, хотя конфиг `lighting_lux_day`/`lighting_lux_night` уже существует в
`SystemAutomationSettingsCatalog.php:181-182,346-347`, а инфраструктура day/night —
в `runtime_plan_builder.py:_build_day_night_config`.

### A.1 Доменная семантика (doc-first)

- Обновить `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` (секция `lighting`):
  зафиксировать поля `on_time`, `off_time`, `brightness` (день), `brightness_night` (ночь, default 0),
  и правило: вне окна `[on_time, off_time)` целевая яркость = `brightness_night`.
- Обновить `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`:
  описать, что `lighting_tick` теперь бывает двух видов — **ON** (вход в окно / внутри окна) и
  **OFF** (выход из окна), и что оба идут через существующий `POST /zones/{id}/start-lighting-tick`.

### A.2 Laravel: передавать желаемое состояние в intent/payload

- `SchedulerCycleOrchestrator.php:506-528`: при переходе границы окна вычислять
  `desired_state = desiredNow ? 'on' : 'off'` и класть в payload job.
- `ScheduleDispatcher.php`: пробросить `desired_state` (`on`/`off`) и `brightness`
  в `request_payload` эндпоинта `/start-lighting-tick`. При отсутствии окна (interval/time-spec) —
  как сегодня, считать `on`.
- `LightingScheduleParser.php`: уже отдаёт `start_time`/`end_time` — без изменений; добавить проброс
  `brightness_night` из lighting config в effective targets, если задан.

### A.3 AE3: план ON/OFF и day/night duty

- `ae3lite/api/contracts.py` → `StartLightingTickRequest`: добавить необязательные
  `desired_state: Literal["on","off"] = "on"` и `brightness_pct: int | None`.
- `cycle_start_planner.py:_build_lighting_tick_plan`:
  - при `desired_state == "off"` строить команду выключения (`set_pwm {duty:0}` /
    `set_relay {state:false}`);
  - при `desired_state == "on"` резолвить duty из day/night config (день/ночь) с приоритетом
    явного `brightness_pct` из запроса, затем targets, затем 100 (текущий fallback).
- Идемпотентность: повторный tick с тем же состоянием — no-op на уровне команды (узел уже в
  нужном состоянии); полагаться на существующую idempotency по intent.

### A.4 Тесты

- AE3 (`make test-ae`): план `off` даёт `set_pwm duty=0`; план `on` берёт day/night duty;
  `pwm`-канал → `set_pwm`, реле-канал → `set_relay`.
- Laravel PHPUnit: orchestrator на границе выхода из окна создаёт job с `desired_state='off'`;
  dispatcher пробрасывает поле в payload.

### Критерии приёмки A

1. E2E: зона с окном фотопериода `06:00–22:00` — в 22:00 (по tz теплицы) приходит **реальная**
   команда выключения света через HL → MQTT.
2. day/night: внутри окна применяется дневная яркость, вне (если свет вообще включается) — ночная.
3. Нет прямой публикации из Laravel; intent lifecycle не сломан; `protocol-check` зелёный.

---

## Этап B — Автодолив бака в фазе роста (`ready`)

### B.0 Проблема

Two-tank контроль уровня работает только на стадиях startup/полива через level switches и
`solution_min` guard (стоп). В фазе роста (`workflow_phase='ready'`) нет контура, который бы
**доливал** бак при падении уровня — только аварийная остановка. Для плодовых с высоким
водопотреблением это означает пустой бак между визитами.

### B.1 Доменная семантика (doc-first)

- Новый документ или секция в `doc_ai/06_DOMAIN_ZONES_RECIPES/WATER_FLOW_ENGINE.md`:
  контур `solution_topup` — по событию `level_switch_changed` (solution level низкий, но не min)
  или по периодическому тику долить чистой воды/раствора до `level_solution_max`.
- Зафиксировать гистерезис (долив от `low` до `max`, не дёргать реле), таймауты, лимит объёма
  за тик и fail-safe (leak/overflow, source empty → стоп + алерт).
- Обновить `doc_ai/04_BACKEND_CORE/AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`: топ-ап как потребитель
  событий уровня в фазе `ready`.

### B.2 AE3: новый task type `solution_topup`

- Новый handler `ae3lite/application/handlers/solution_topup.py`: guard `workflow_phase='ready'`,
  открыть клапан/насос долива, ждать `level_solution_max` или таймаут, закрыть, событие
  `solution_topup_done` / при таймауте `solution_topup_timeout` + alert.
- Триггер: (а) реактивно — `level_monitor` при переходе solution-уровня в low будит worker;
  (б) периодически — Laravel dispatch по расписанию (как lighting).
- Переиспользовать инфраструктуру `level_switch_semantics.py`, `zone_runtime_monitor.py`.

### B.3 Laravel

- Расписание/триггер топ-апа (если периодический вариант): аналог lighting в
  `ScheduleDispatcher` (`isAeDispatchableTaskType` + endpoint `/start-solution-topup` или
  расширение существующего механизма intent).
- Миграция при новом `intent_type` + `DATA_MODEL_REFERENCE.md`.

### B.4 Тесты

- AE3: топ-ап доливает до max и завершается; таймаут → fail-closed + alert; leak во время долива → стоп.
- E2E (node_sim two-tank profile): падение уровня раствора в `ready` → топ-ап → уровень восстановлен.

### Критерии приёмки B

1. В фазе `ready` при низком уровне раствора автоматически выполняется долив до безопасного уровня.
2. Все fail-safe (overflow, source empty, leak, timeout) поднимают alert и оставляют актуаторы в safe state.
3. Не конфликтует с активным поливом/коррекцией (single active task на зону сохраняется).

---

## Этап C — Контроль температуры раствора

### C.0 Проблема

Канал `solution_temp_c` присутствует в firmware/симуляторе и пишется в телеметрию
(`NODE_CHANNELS_REFERENCE.md:96`), но AE3 его **не использует**: нет ни алертов на выход за
пределы, ни управления нагревателем/чиллером.

### C.1 Минимальный вариант (обязательный): алерты порогов

- Добавить в effective targets/recipe фазу пороги `solution_temp` (`min`/`max`/target).
- history-logger или AE3: при выходе `solution_temp_c` за пределы N минут → бизнес-алерт
  (`biz_solution_temp_high` / `biz_solution_temp_low`) в `error_codes.json`/`alert_codes.json`.
- Prometheus alert rule + панель Grafana.

### C.2 Полный вариант (опциональный, при наличии актуатора): контур регулирования

- Реле/актуатор нагрева/охлаждения на relay_node.
- Простой bang-bang контроллер с гистерезисом в AE3 (по образцу greenhouse climate rule-engine),
  single-writer, fail-safe при отказе сенсора (OOB → стоп нагрева, алерт).
- Спецификация: секция в `ZONE_CONTROLLER_FULL.md`.

### Критерии приёмки C

1. Выход t° раствора за агрономические пределы всегда даёт алерт (внешний канал — этап E).
2. При наличии актуатора t° удерживается в коридоре с гистерезисом; отказ сенсора → безопасный стоп.

---

## Этап D — Подмена раствора / базовый CIP

### D.0 Проблема

Для длинных циклов плодовых раствор деградирует; сейчас нет автоматического drain/refill.
`clean_fill` — только наполнение чистой водой в рамках startup, не полный цикл замены.

### D.1 Первый шаг — полуавтомат (рекомендуется начать с него)

- Тип задачи `solution_change`: по кнопке оператора или расписанию **с подтверждением**.
- Переиспользовать стадии two-tank: drain текущего раствора → clean_fill → solution_fill →
  prepare_recirc → ready.
- Явные точки подтверждения оператора (UI) перед drain и после refill.

### D.2 Полный автомат (позже)

- Планирование `solution_change` из фаз рецепта (каждые N дней) без участия оператора,
  с уведомлением в Telegram о начале/завершении.
- Опциональный CIP-цикл (промывка с раствором санитайзера) как отдельная стадия.

### D.2 Спецификация

- Секция в `RECIPE_ENGINE_FULL.md` / `CORRECTION_CYCLE_SPEC.md`; вывести `solution_change`
  из списка «out of AE3 v1 scope» в `ae3lite.md` §1 с описанием стадий.

### Критерии приёмки D

1. Оператор может запустить подмену раствора одной командой; система проходит drain→refill→ready.
2. Все стадии имеют fail-safe и уведомления; частичный сбой не оставляет зону в опасном состоянии.

---

## Этап E — Внешний алертинг в Telegram (параллельно A–D)

### E.0 Проблема

Алерты сейчас видны только в Web UI при живом WebSocket. Для автономии с визитами раз в неделю
нужен push во внешний канал. В prod Alertmanager SMTP/Telegram — placeholders (аудит K11),
webhook в Laravel без токена.

### E.1 Telegram-бот

- Notification-канал в Laravel: `TelegramChannel` (Laravel Notifications) или прямой клиент
  Bot API; конфиг `config/services.php` (`telegram.bot_token`, chat_id/список подписчиков через env).
- Роутинг: критичные бизнес-алерты (`biz_correction_exhausted`, `biz_irrigation_*`, E-STOP,
  `biz_solution_temp_*`, node offline) и инфраструктурные (ServiceDown, брокер, БД) → Telegram.
- Дедупликация/тихий период (не спамить повторами одного алерта), severity-фильтр.

### E.2 Alertmanager → Laravel (закрыть K11)

- Реализовать R1.1 из reliability-плана: bearer token на webhook (dev+prod),
  `ALERTMANAGER_WEBHOOK_SECRET` в compose, non-placeholder receivers.
- Alertmanager Prometheus-алерты → Laravel webhook → `AlertService` → Telegram.

### E.3 Тесты

- Laravel PHPUnit: notification отправляется для критичного алерта (fake Telegram transport);
  тихий период подавляет дубли.
- Интеграция: тестовый алерт из Prometheus доходит до Telegram-заглушки в dev.

### Критерии приёмки E

1. Критичный алерт (например, correction exhausted) приходит в Telegram в течение < 1 мин.
2. Alertmanager webhook аутентифицирован; в prod-конфиге нет placeholder-получателей без пометки.

---

## Этап F — Firmware fail-safe при потере связи (перед реальным железом)

> Реализуется в связке с этапом R5 reliability-плана. Обязателен **до** первого запуска на
> реальном железе — на стенде/HIL можно вести параллельно.

### F.1 Link-loss fail-safe (K1)

- Единая policy в `node_framework`: `link_loss_timeout_sec` (NodeConfig, зеркалит `fail_safe_guards`).
- При MQTT DISCONNECTED дольше таймаута: насосы (вкл. latched) — emergency stop; реле — safe state;
  свет — выключить. Публиковать `event_code="link_loss_failsafe"` после reconnect.
- Файлы: `ph_node_init.c`, `pump_node_init.c`, `pump_driver.c`, `relay_driver.c`,
  `storage_irrigation_node`.

### F.2 Запрет legacy HMAC в release (K2)

- `node_command_handler.c`: `allow_legacy_hmac` только под dev-флагом сборки; release — reject
  неподписанных команд (`hmac_required`).

### F.3 Честная телеметрия и ответы на невалидные команды

- Убрать фиктивные дефолты pH 6.5 / EC 1.2 (R5.3); NaN климата не публиковать; при невалидной
  команде с извлечённым `cmd_id` слать `INVALID`.

### Критерии приёмки F

1. HIL: обрыв MQTT при работающем насосе → останов в пределах `link_loss_timeout_sec`.
2. Release-сборка отклоняет неподписанные команды; `protocol-check` зелёный; MQTT-доки обновлены.

---

## 11. Предусловие: закрыть reliability-хвост R3/R4

В рабочем дереве уже лежат незакоммиченные тесты и правки reliability (см. git status):
`test_ae3lite_lease_heartbeat_fail_closed.py`, `test_ae3lite_intent_sync_retry.py`,
`test_ae3lite_reliability_metrics.py`, `history-logger/tests/test_reliability_r3.py` и
изменения в `redis_queue.py`, `worker.py`, `stale_task_reconcile.py`, `telemetry_processing.py`.

**До начала этапов A–D** нужно:

1. Довести и закоммитить эту работу (R3 надёжная очередь телеметрии, R4 lease/janitor/intent sync).
2. Прогнать `make test-ae` и HL pytest до зелёного.
3. Только затем строить агроконтуры поверх стабильного пайплайна — иначе PID/полив/долив будут
   принимать решения по потенциально потерянной/устаревшей телеметрии.

Полный список critical K1–K13 и этапов R1–R7 — в `AUDIT_2026_07_07_RELIABILITY_PLAN.md`.

---

## 12. Порядок выполнения (рекомендуемый)

| Неделя | Работы |
|--------|--------|
| 1 | Предусловие §11 (закоммитить/довести R3/R4); старт E (Telegram) параллельно |
| 2 | Этап A (освещение day/night + OFF) — полный цикл doc→code→test→e2e |
| 3 | Этап B (автодолив) + завершение E |
| 4 | Этап C (t° раствора: минимум — алерты) |
| 5+ | Этап D (подмена раствора, полуавтомат), затем F перед выходом на железо |

## 13. Definition of Done мастер-плана

1. Освещение: гарантированный OFF в конце фотопериода + day/night яркость (этап A).
2. Автодолив бака в фазе роста с полным набором fail-safe (этап B).
3. Контроль t° раствора: минимум алерты, при наличии актуатора — контур (этап C).
4. Подмена раствора доступна оператору одной командой (этап D).
5. Критичные алерты доходят в Telegram; Alertmanager webhook аутентифицирован (этап E).
6. Firmware fail-safe при потере связи + запрет legacy HMAC (этап F, перед железом).
7. Reliability-хвост R3/R4 закоммичен, все suites зелёные (предусловие §11).
8. Документация синхронизирована: `EFFECTIVE_TARGETS_SPEC.md`, `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`,
   `WATER_FLOW_ENGINE.md`, `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`, `ae3lite.md`,
   `ERROR_CODE_CATALOG.md`, `ALERTS_AND_NOTIFICATIONS_CHANNELS.md`, `NODE_CONFIG_SPEC.md`.

---

**См. также:** `AUDIT_2026_07_07_RELIABILITY_PLAN.md`, `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`,
`doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `doc_ai/04_BACKEND_CORE/ae3lite.md`,
`doc_ai/06_DOMAIN_ZONES_RECIPES/GREENHOUSE_CLIMATE_CONTROL_PLAN.md`.
