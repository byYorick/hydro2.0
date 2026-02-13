# AUTOMATION_LOGIC_AI_AGENT_PLAN.md
# План выполнения для ИИ-агента: рефактор логики автоматики (scheduler + automation-engine)

**Дата:** 2026-02-13  
**Статус:** Draft/Active  
**Владелец:** AI Agent (cross-layer)  
**Приоритет:** высокий

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.  
Breaking-change: контракт runtime-логики автоматики обновляется; дублирование recipe-targets в logic-конфиге удаляется.

---

## 1) Цель

Перевести систему на строгую модель:

1. `Recipe` хранит только целевые значения фаз выращивания (targets/limits).
2. `Automation Logic` хранит только операционную логику исполнения:
   - расписания (tick-интервалы, окна);
   - алгоритмы принятия решения `run/skip/retry/fail`;
   - state-machine шагов операций;
   - safety/rate/attempt лимиты;
   - fallback-поведение.

Ключевое правило:
- scheduler только предлагает задачу (`tick`);
- automation-engine принимает решение и исполняет;
- успех только при `DONE` и/или измеряемом подтверждении эффекта.

---

## 2) Зафиксированные решения (по итогам обсуждения)

1. Разделение `Recipe` и `Automation Logic` подтверждено.
2. Scheduler отправляет абстрактные задачи, не device-команды.
3. Для drip-полива добавляются ноды/каналы сенсоров почвы:
   - влажность субстрата;
   - температура субстрата.
4. Для климата добавляется наружный датчик скорости ветра.
5. Skip-причины (минимум):
   - уже идёт операция;
   - вне окна;
   - цель достигнута;
   - safety-блок.
6. `low_water` и `nodes_unavailable`:
   - не считаются окончательным skip;
   - создают alerts;
   - запускают retry (до 10 попыток).
7. При online-коррекции порядок дозирования:
   - сначала `EC`, затем `pH`.
8. При недостижении корректного раствора во время полива:
   - остановить полив;
   - переключить контур на коррекцию “бак -> бак”;
   - выполнить отдельную логику коррекции.
9. Смена раствора поддерживает триггеры:
   - по расписанию;
   - по событию;
   - вручную.
10. Для топологий `2 бака` и `3 бака` нужны разные state-machine.
11. Если внешние climate-ноды недоступны:
   - fallback: только логирование (без активного открытия/вентиляции по ним).
12. Итог задачи должен содержать расширенный контроль:
   - `decision`, `reason_code`, `action_required`, `executed_steps`, `safety_flags`, `next_due_at`, и др.
13. Шаги state-machine в event-хранилище сохраняются агрегированным summary.

---

## 3) Канонические типы задач (scheduler -> automation-engine)

1. `irrigation_tick`
   - проверка необходимости полива;
   - решение `run/skip`;
   - при `run`: полив + online EC/pH коррекция + контроль эффекта.
2. `solution_prepare_tick`
   - подготовка рабочего раствора до recipe-targets.
3. `solution_change_tick`
   - смена раствора (включая опциональную промывку по флагу).
4. `climate_tick`
   - управление вентиляцией/форточками с учётом внешних ограничений.
5. `lighting_tick`
   - управление светом по окнам/интервалам.
6. `diagnostics_tick`
   - проверка готовности контуров и узлов.
7. `safety_tick`
   - контроль safety-ограничений и блокировок.

---

## 4) Контракт данных: что хранится где

## 4.1 Recipe (источник целей)
- `ph/ec/temp/humidity/light` targets;
- лимиты и допустимые диапазоны;
- фазовые окна/расписания, относящиеся к агрономической цели.

## 4.2 Automation Logic Profile (источник поведения)
- интервалы и окна tick-задач;
- алгоритмы decision-layer;
- retry/backoff/attempt limits;
- safety thresholds;
- execution-state параметры (таймауты, max_steps, fail-conditions);
- режимы `setup|working`.

Запрет:
- targets из recipe не должны дублироваться в automation logic profile.

---

## 5) Требования к алгоритмам (MVP v1)

## 5.1 Drip irrigation decision
Вход:
- recipe targets (через effective-targets);
- soil moisture/temp;
- ambient temp;
- состояние контуров и safety.

Базовые правила:
1. Норма влажности (временный дефолт): `80% ±10%`.
2. Если влажность `ok` и нет жара -> `skip`.
3. Если влажность `ok`, но высокая температура -> `run_reduced` (30% базовой дозы).
4. Если влажность ниже нормы -> `run_full`.
5. Если `low_water`/`nodes_unavailable` -> alert + retry (до 10 попыток).

## 5.2 Полив и коррекция
1. До старта проверить наличие раствора в баке (уровень).
2. Во время полива:
   - online коррекция по проточному узлу;
   - порядок: EC -> pH;
   - PID-регуляторы обязательны.
3. Если корректировка неуспешна:
   - аварийно остановить полив;
   - запустить баковую коррекцию (контур рециркуляции в бак);
   - зафиксировать outcome как `failed/recovered`.

## 5.3 Solution prepare/change
1. Готовность раствора: соответствие recipe-targets.
2. Смена раствора:
   - триггеры: schedule/event/manual;
   - промывка опциональна (флаг с фронта);
   - завершение этапов по датчикам уровня.
3. Для `2 баков` и `3 баков` использовать разные state-machine.

## 5.4 Climate
1. Решение только в automation-engine по `climate_tick`.
2. Ограничения:
   - сильный ветер -> форточки не открывать;
   - низкая наружная температура -> форточки не открывать и вентиляцию не включать.
3. Пороги ветра/температуры настраиваются в automation profile.

---

## 6) Новые ноды/каналы (обязательный минимум)

1. `soil_sensor` (или канонический type + metric map)
   - `soil_moisture`
   - `soil_temp`
2. `weather_sensor`
   - `wind_speed`
   - `outside_temp` (если отсутствует в текущем внешнем канале)

Требование:
- добавить канонические node/channel описания в спецификации и обработчики ingestion.

---

## 7) Frontend: конфигуратор логики

Цель:
- единый конфигуратор в `Zone Automation` и в `Setup Wizard`.

Настраиваемые блоки:
1. Tick-интервалы и окна задач.
2. Алгоритмы decision-layer:
   - skip/run rules;
   - reduced-run policy (30%);
   - retry/backoff policy (10 attempts).
3. Safety thresholds.
4. Параметры solution prepare/change, включая флаг промывки.
5. Внешние climate-ограничения (ветер/температура).
6. PID-настройки (или профиль PID).

Запрет:
- target-поля recipe не редактируются в логике автоматики.

---

## 8) API/Contracts (целевое состояние)

1. `POST /api/zones/{zone}/automation-logic-profile`
   - сохраняет только behavior config;
   - `mode=setup|working`.
2. `POST /api/zones/{zone}/commands type=GROWTH_CYCLE_CONFIG`
   - содержит `profile_mode`;
   - не содержит recipe-target дубликатов.
3. Internal `effective-targets`:
   - recipe targets + runtime behavior extensions;
   - явное разделение `targets` и `execution/logic`.
4. Scheduler task result:
   - обязательные поля контроля:
     - `decision`
     - `reason_code`
     - `action_required`
     - `executed_steps`
     - `safety_flags`
     - `next_due_at`
     - `measurements_before_after`
     - `commands_effect_confirmed`
     - `error_code` (если есть)

---

## 9) План работ по этапам (для ИИ-агента)

### Этап A0: Спецификация и freeze контрактов
- Scope:
  - `doc_ai/04_BACKEND_CORE`, `doc_ai/05_DATA_AND_STORAGE`, `doc_ai/06_DOMAIN_ZONES_RECIPES`.
- Changes:
  - зафиксировать новые task types, state-machine, payload/response схемы.
- Checks:
  - consistency review между doc-и кодом.
- Gate:
  - согласованные спецификации без противоречий.

### Этап A1: Модель данных и миграции
- Scope:
  - Laravel migrations/models + data reference.
- Changes:
  - структуры для behavior-конфига, retry/safety/pid параметров.
- Checks:
  - миграции up/down, feature tests.
- Gate:
  - схема применима и обратима.

### Этап A2: Backend API и effective-targets merge
- Scope:
  - Laravel services/controllers/requests.
- Changes:
  - удалить дубли recipe-targets из logic-профиля;
  - merge behavior в execution-ветки.
- Checks:
  - unit/feature tests.
- Gate:
  - контракт API стабилен.

### Этап A3: Scheduler planner-only update
- Scope:
  - `backend/services/scheduler/*`.
- Changes:
  - dispatch только абстрактных tick задач.
- Checks:
  - pytest scheduler.
- Gate:
  - нет device-level dispatch из scheduler.

### Этап A4: Automation-engine decision/state-machine
- Scope:
  - `backend/services/automation-engine/*`.
- Changes:
  - decision-layer, state-machine 2/3 tanks, retry policy, PID integration.
- Checks:
  - unit/integration pytest + summary outcomes.
- Gate:
  - DONE/measure-based success semantics соблюдены.

### Этап A5: Frontend configurator unification
- Scope:
  - Zone tab + Setup wizard.
- Changes:
  - единый конфигуратор;
  - убрать редактирование recipe-targets в logic UI.
- Checks:
  - typecheck + vitest.
- Gate:
  - идентичный behavior-config UI в двух местах.

### Этап A6: Ноды/каналы и ingestion
- Scope:
  - node registry, history-logger ingestion, docs.
- Changes:
  - новые node/channel типы и обработчики.
- Checks:
  - ingestion tests + smoke telemetry.
- Gate:
  - automation-engine получает валидные входы от новых датчиков.

### Этап A7: E2E и наблюдаемость
- Scope:
  - e2e scenarios + alerts + dashboards.
- Changes:
  - сценарии полива/коррекции/смены/климата;
  - алерты и summary логирование.
- Checks:
  - e2e pass.
- Gate:
  - воспроизводимость в dev/staging.

---

## 10) Критерии приёмки

1. В logic profile нет дублей recipe-targets.
2. Scheduler dispatch-ит только `tick`-задачи.
3. Automation-engine принимает decision `run/skip/retry/fail` на основе правил.
4. Для drip учитываются `soil_moisture + soil_temp + ambient_temp`.
5. `low_water`/`nodes_unavailable` -> alerts + retry<=10.
6. Online коррекция в поливе: EC->pH.
7. При неуспехе online коррекции полив останавливается и запускается баковая коррекция.
8. Отдельные state-machine для `2 баков` и `3 баков`.
9. Climate учитывает `wind_speed` и `outside_temp` ограничения.
10. Task outcome содержит расширенный summary-контракт.

---

## 11) Открытые вопросы (требуют уточнения до production)

1. Точные пороги:
   - `high temperature`;
   - `strong wind`;
   - `low outside temperature`.
2. Формула reduced irrigation (кроме текущего дефолта 30%).
3. PID параметры по умолчанию для online и баковой коррекции.
4. Точные команды/каналы переключения контура “бак -> бак”.
5. Детали fallback политики при отсутствии внешних climate датчиков.

Примечание:
- до уточнения использовать временные дефолты и обязательный feature-flag rollout.

---

## 12) Формат отчёта ИИ-агента по каждому этапу

1. `Scope`
2. `Changes`
3. `Checks`
4. `Gate`
5. `Risks/Assumptions`
6. `Rollback`

