# AE3 Real-Hardware Logic Gaps

**Дата:** 2026-04-09  
**Статус:** AUDIT NOTES  
**Источник:** real-hardware E2E прогоны на test node (`localhost:1884`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Назначение

Документ фиксирует не тестовые флаки и не дефекты сценариев, а именно логические зазоры
в текущем AE3 runtime, которые проявились во время real-hardware прогонов.

Это рабочий аудит для следующего этапа рефакторинга логики автоматики.

---

## 1. Наблюдаемые логические несостыковки

### 1.1 `ready` объявляется слишком рано относительно реальной химической стабилизации

Сейчас родительские stage считают цель достигнутой через `_targets_reached()`:
- [`base.py:685`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/base.py#L685)

Фактическая логика:
- берётся decision window по `PH` и `EC`;
- проверка идёт по tolerance вокруг `target_ph` и `target_ec`;
- при попадании в этот диапазон stage считает цель достигнутой.

Это напрямую завершает:
- `solution_fill_check` в [`solution_fill.py:277`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L277)
- `prepare_recirculation_check` в [`prepare_recirc.py:133`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/prepare_recirc.py#L133)

Что видно на real hardware:
- сценарий `E101_ae3_two_tank_realhw_setup_ready` регулярно завершает task как `completed`;
- workflow доходит до `ready`;
- при этом отдельная более узкая проверка “реально вошли в operational band” уходит в optional timeout.

Вывод:
- текущая семантика `ready` ближе к “формально в допуске”, чем к “раствор реально стабилизирован в рабочем диапазоне”.

Риск:
- зона может перейти в `ready` раньше, чем смесь реально готова для дальнейшего использования.

---

### 1.2 `solution_fill` фактически даёт только одно correction-window на весь этап fill

После исчерпания correction attempts общий correction handler возвращает:
- повторный вход в `solution_fill_check` с увеличенным `stage_retry_count`
- см. [`correction.py:1337`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/correction.py#L1337)

Но затем сам `solution_fill_check` делает short-circuit:
- если `stage_retry_count > 0`, новая in-flow correction больше не запускается;
- handler только продолжает polling;
- см. [`solution_fill.py:214`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L214)

Фактическая семантика:
- одна неудачная correction window во время fill выключает дальнейшие попытки коррекции до конца stage;
- stage после этого живёт только до `solution_max` или до timeout.

Почему это логически спорно:
- `solution_fill` физически ещё продолжается;
- условия в баке могут измениться;
- новая корректировка в рамках того же fill-stage может быть осмысленной;
- но текущий runtime это запрещает уже после первого exhausted/no-effect окна.

Риск:
- stage доходит до полного бака без повторной попытки довести раствор до цели, хотя время и вода ещё есть.

---

### 1.3 Сигнал “бак заполнен” сильнее химической цели

В `solution_fill_check` есть два быстрых пути завершения:
- runtime event `SOLUTION_FILL_COMPLETED` сразу ведёт в `_completed_outcome()`:
  [`solution_fill.py:82`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L82)
- `solution_max.is_triggered` делает то же самое:
  [`solution_fill.py:177`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L177)

Дальше `_completed_outcome()` уже только выбирает:
- `solution_fill_stop_to_ready`
- или `solution_fill_stop_to_prepare`
- см. [`solution_fill.py:265`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L265)

Но важное следствие такое:
- как только node решила, что бак полный, окно in-flow correction фактически закрывается;
- даже если stage deadline ещё позволяет поработать;
- даже если одна дополнительная доза была бы полезна.

Это уже проявилось на real hardware:
- real-hw сценарии пришлось стабилизировать так, чтобы не поднимать `level_solution_max` слишком рано;
- иначе AE3 завершал fill-stage раньше, чем успевала пройти ожидаемая EC correction.

Вывод:
- в текущей модели “уровень/завершение fill” доминирует над химической логикой;
- фактически химия подстраивается под механику fill, а не наоборот.

Риск:
- node и AE3 корректно согласованы по stop-semantics;
- но бизнес-результат “получить нужный раствор” остаётся вторичным относительно “бак уже полный”.

---

## 2. Что это значит для следующего рефакторинга

Приоритетные направления:

1. Развести понятия:
   - `tank_full`
   - `chemically_ready`
   - `workflow_ready`

2. Явно определить, может ли `solution_fill` открывать больше одного correction-window в рамках одного fill-stage.

3. Уточнить приоритеты:
   - что делать, если `solution_max = true`, но химия ещё не в целевом operational band;
   - должен ли stage завершаться немедленно;
   - или должен переводиться в отдельный post-fill conditioning path.

4. Согласовать бизнес-семантику `ready`:
   - `ready` по широкому tolerance;
   - или `ready` только по более строгому рабочему диапазону.

---

## 3. Короткий вывод

После реальных прогонов главный логический долг AE3 сейчас не в event-ingest и не в fail-safe.

Главный долг в том, что:
- `ready` определяется слишком мягко;
- `solution_fill` слишком рано отказывается от повторной коррекции;
- сигнал “бак полон” сильнее сигнала “раствор готов”.

Именно это сейчас сильнее всего влияет на фактическое поведение автоматики на железе.
