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

## 0.1 Текущий статус после первых runtime-дельт

На момент этого снимка документ уже частично исторический:

- `solution_fill` больше не завершает `no-effect` через скрытый `poll`/re-entry loop;
  canonical fail-closed path теперь ведёт в `solution_fill_timeout_stop`
  (см. [`correction.py:2176`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/correction.py#L2176)).
- переходы в `*_stop_to_ready` больше не опираются только на мягкий `_targets_reached()`:
  для `workflow_ready` используется отдельная проверка `_workflow_ready_reached()`
  с explicit ready band по `target_*_min/max`, если он доступен
  (см. [`base.py:725`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/base.py#L725)).
- `solution_fill` при `tank_full` теперь уводит в `solution_fill_stop_to_ready` только если
  подтверждён `workflow_ready`, иначе переводит в post-fill conditioning path
  `solution_fill_stop_to_prepare`
  (см. [`solution_fill.py:277`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L277),
  [`correction.py:204`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/correction.py#L204)).
- `prepare_recirculation_check` и correction success в recirculation теперь тоже требуют
  explicit `workflow_ready`, а не только correction-success по мягкому tolerance
  (см. [`prepare_recirc.py:133`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/prepare_recirc.py#L133),
  [`correction.py:465`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/correction.py#L465)).

Следовательно, разделы ниже нужно читать как:
- что наблюдалось на real hardware до этих дельт;
- какие из зазоров уже закрыты;
- какие ещё остаются открытыми.

---

## 1. Наблюдаемые логические несостыковки

### 1.1 `ready` объявляется слишком рано относительно реальной химической стабилизации

**Статус:** частично закрыто.

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

Актуализация:
- после первой runtime-дельты `workflow_ready` больше не равен просто soft tolerance around target;
- если в runtime уже есть explicit `target_ph_min/max` и `target_ec_min/max`, переход в `ready`
  подтверждается именно по этому ready band;
- fallback на `prepare_tolerance` остаётся только там, где explicit ready band отсутствует.

Что всё ещё открыто:
- runtime пока не требует `2` подряд ready-window или отдельный hold-time;
- то есть проблема “слишком ранний `ready`” снижена, но не исчерпана полностью.

Риск:
- зона может перейти в `ready` раньше, чем смесь реально готова для дальнейшего использования.

---

### 1.2 `solution_fill` фактически даёт только одно correction-window на весь этап fill

**Статус:** в исходной формулировке больше не актуально; закрыто частично и переопределено.

После исчерпания correction attempts общий correction handler возвращает:
- повторный вход в `solution_fill_check` с увеличенным `stage_retry_count`
- см. [`correction.py:1337`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/correction.py#L1337)

Но затем сам `solution_fill_check` делает short-circuit:
- если `stage_retry_count > 0`, новая in-flow correction больше не запускается;
- handler только продолжает polling;
- см. [`solution_fill.py:214`](/home/georgiy/esp/hydro/hydro2.0/backend/services/automation-engine/ae3lite/application/handlers/solution_fill.py#L214)

Актуализация:
- ordinary attempt caps в `solution_fill` больше не должны закрывать correction window раньше stage timeout;
- при `no-effect` runtime теперь идёт в явный fail-closed `solution_fill_timeout_stop`,
  а не в скрытый `poll` с дальнейшей неоднозначной семантикой;
- canonical fill-policy теперь: continuous correction until `no-effect` fail-closed
  или stage timeout.

Почему это логически спорно:
- `solution_fill` физически ещё продолжается;
- условия в баке могут измениться;
- новая корректировка в рамках того же fill-stage может быть осмысленной;
- но текущий runtime это запрещает уже после первого exhausted/no-effect окна.

Что всё ещё открыто:
- документированный вопрос уже не в “одно окно или много окон”, а в том,
  достаточно ли текущего fail-closed на `no-effect`, или нужен более богатый post-fill path
  и/или дополнительная логика повторного допуска коррекции после смены условий в баке.

---

### 1.3 Сигнал “бак заполнен” сильнее химической цели

**Статус:** частично закрыто.

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

Актуализация:
- гидравлический факт `tank_full` по-прежнему завершает сам fill-path;
- но он больше не означает автоматический переход в `ready`;
- при `tank_full && !workflow_ready` runtime обязан уходить в `solution_fill_stop_to_prepare`
  и дальше в `prepare_recirculation`, а не завершать workflow как ready.

Вывод после дельты:
- “бак полон” всё ещё сильнее в части остановки fill-механики;
- но уже не сильнее в части финального business-result `workflow_ready`.

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

После уже внесённых дельт остаются приоритетными:

1. Явно зафиксировать в каноне разницу между `correction_success` и `workflow_ready`.
2. Решить, нужен ли для `workflow_ready` дополнительный temporal guard:
   - `N` подряд ready-window;
   - или minimum hold-time в ready band.
3. Проверить real-hardware/e2e, что сценарии `setup_ready` и `ready_during_recirculation`
   действительно теперь проходят только через strict ready band, а не через soft tolerance.

---

## 3. Короткий вывод

После реальных прогонов главный логический долг AE3 сейчас не в event-ingest и не в fail-safe.

Главный долг после уже внесённых runtime-дельт сместился:
- мягкий `ready` частично ужесточён, но ещё не подтверждается temporal stability guard;
- fail-closed семантика `no-effect` в fill уже приведена к явному terminal path;
- `tank_full` больше не даёт автоматический `ready`, но post-fill conditioning ещё требует
  подтверждения на real hardware.

То есть следующий главный долг уже не в самом разделении `tank_full`/`ready`,
а в доведении строгой семантики `workflow_ready` до полностью подтверждённого real-hardware контракта.
