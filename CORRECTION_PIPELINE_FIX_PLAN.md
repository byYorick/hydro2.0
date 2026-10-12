---
name: Correction Pipeline Fix Plan
description: План исправления дедлайнов, target outcome, sensor mode, PID deadband и эксплуатационных рисков AE3-Lite correction pipeline.
version: 1.0.0
last_updated: 2026-10-12
maintained_by: Hydro 2.0 Automation Team
status: planned
---

# План исправления pipeline корректировок pH/EC

## 1. Цель

Устранить дефекты, найденные при аудите реального прогона зоны 3, и обеспечить следующие свойства:

- опубликованная дозирующая команда никогда не теряется при достижении stage deadline;
- фактически выполненная доза всегда отражается в `ae_commands` и `pid_state`;
- pH и EC сходятся к setpoint в пределах PID deadband, а не считаются достигнутыми на границе широкого recipe-диапазона;
- завершение гидравлики полива и результат химической коррекции учитываются отдельно;
- недостижение целей наблюдаемо и не маскируется как успешная коррекция;
- persistent sensor mode не активируется повторно перед каждой дозой;
- исправления расширяют существующую AE3-Lite correction sub-machine, не создавая параллельный runtime.

## 2. Основание

На задачах зоны 3 подтверждены следующие случаи:

| Task | Наблюдение | Риск |
|---|---|---|
| `32` | Доза `ae3-t32-z3-s39` физически завершилась после stage deadline, но `ae_commands.terminal_status` остался `NULL` | Неучтённая физическая доза и рассинхронизация PID |
| `32` | 11 решений и 11 повторных активаций sensor mode | Потеря correction budget |
| `34` | Цель EC `1.4`, pH `5.8`; последнее решение EC `0.532`, pH `6.7265`; задача завершена как `completed_run` | Недостижение целей скрыто от оператора |
| `32`, `34` | Большинство доз ограничены clamp, а correction window заканчивается раньше сходимости | Контур ограничен временем и производительностью |

Дополнительно обнаружены 20 `accepted`-команд без terminal status у уже terminal-задач. Они требуют безопасной reconciliation, а не ручного изменения БД.

## 3. Инварианты и ограничения

| Инвариант | Требование |
|---|---|
| Command pipeline | Только `Laravel scheduler -> Automation Engine -> History Logger -> MQTT -> ESP32` |
| MQTT authority | Запрещён прямой publish из Laravel или Automation Engine |
| Runtime | Использовать существующие `CorrectionHandler`, `CorrectionPlanner` и command gateway |
| Correction action | Не более одного химического correction action за tick |
| Persistence | `hold_until`, `last_dose_at`, PID state и terminal command status сохраняются в БД |
| Safety | Missing/stale telemetry, calibration, binding и policy остаются fail-closed |
| Sensor mode | Сохранить stage-managed semantics; persistent stages не реактивируют активные датчики |
| БД | Только Laravel migrations; в текущем плане изменение схемы не ожидается |
| Scope | Не добавлять Python-сервис, AE3 `task_type`, ingress API или authority document type |
| Compatibility | Не менять MQTT topics/payload и History Logger API без отдельного согласования |

## 4. Целевая модель завершения

Гидравлический и химический результаты должны быть независимыми:

| Hydraulic outcome | Chemistry outcome | Итог |
|---|---|---|
| Полив корректно остановлен | `targets_achieved` | Task `completed`, `CORRECTION_COMPLETE`, без chemistry alert |
| Полив корректно остановлен | `targets_not_achieved` | Task может остаться `completed`, но получает явный chemistry warning/event; автоматический retry полива запрещён |
| Команда дозирования не получила terminal status | `unknown` | Task не считается безопасно завершённой; fail-safe stop, alert и reconciliation |
| Command terminal error/no-effect | `failed` | Существующий fail-closed переход и alert |

`completed_run` не должен интерпретироваться как подтверждение достижения pH/EC. В `AE_TASK_COMPLETED` и diagnostics необходимо передавать отдельный `chemistry_outcome`.

## 5. Этапы реализации

### P0. Не терять in-flight mutating commands на дедлайне

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/infrastructure/gateways/command_publish_pipeline.py`
- `backend/services/automation-engine/ae3lite/infrastructure/gateways/sequential_command_gateway.py`
- `backend/services/automation-engine/ae3lite/application/handlers/correction.py`
- существующий startup/recovery reconciliation path
- соответствующие unit/integration tests

Работы:

1. Перед публикацией `dose` вычислять минимальный необходимый бюджет:
   - declared `duration_ms`;
   - command poll margin;
   - резерв на безопасную остановку стадии.
2. Если бюджета недостаточно, не публиковать новую дозу и вернуть deadline outcome до создания физического side effect.
3. После успешной публикации не использовать stage deadline как terminal deadline команды.
4. Дождаться `DONE`/terminal error в пределах собственного command poll timeout.
5. При `DONE` сохранить terminal status, фактическую дозу, `last_dose_at`, hold и PID update до stage transition.
6. При command poll timeout выполнить существующий fail-safe stop, создать alert и завершить задачу через fail-closed path, а не через graceful success.
7. Расширить существующую startup/recovery reconciliation для `accepted + terminal_status IS NULL`, включая terminal-задачи. Не создавать новый сервис.
8. Добавить идемпотентный repair/reconciliation прогон для накопленных строк. Ручной `UPDATE` запрещён.

Критерии приёмки:

- после terminal task нет новой дозирующей строки `accepted/NULL`;
- доза, получившая `DONE` после stage deadline, отражена в `ae_commands` и `pid_state`;
- недостаточный stage budget не создаёт команду в History Logger;
- terminal timeout приводит к fail-safe и alert, но не к `completed_run`;
- restart во время ожидания команды корректно восстанавливает reconciliation.

### P0. Сделать target outcome обязательным

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/application/handlers/irrigation_check.py`
- `backend/services/automation-engine/ae3lite/application/handlers/correction.py`
- `backend/services/automation-engine/ae3lite/domain/services/correction_transition_policy.py`
- `backend/services/automation-engine/ae3lite/application/use_cases/workflow_router.py`
- Laravel presenter/read model, отображающий результат execution run

Работы:

1. На deadline получить свежий fail-closed target snapshot через существующий decision-window path.
2. Передать реальный `targets_reached` в transition policy вместо `None`.
3. При достижении setpoint испускать `CORRECTION_COMPLETE` с конечными pH/EC, targets и deadbands.
4. При недостижении испускать `CORRECTION_TARGETS_NOT_ACHIEVED` либо канонически оформить существующий `targets_not_achieved`.
5. Создать business alert с конечными значениями, targets, deadbands, task id и причиной завершения.
6. Добавить `chemistry_outcome` в terminal diagnostics/UI без автоматического retry гидравлического полива.
7. Запретить появление `CORRECTION_COMPLETE`, если хотя бы один разрешённый контур вне deadband.
8. Отдельно зафиксировать policy для unavailable/stale telemetry на deadline: outcome `unknown`, fail-closed alert.

Критерии приёмки:

- сценарий EC `0.532` / pH `6.7265` при цели `1.4` / `5.8` не выглядит как успешная коррекция;
- оператор видит `targets_not_achieved` и финальные измерения;
- успешный hydraulic stop не запускает повторный полив автоматически;
- `CORRECTION_COMPLETE` появляется только при попадании в PID deadband.

### P1. Убрать повторную активацию sensor mode

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/application/services/sensor_mode_controller.py`
- `backend/services/automation-engine/ae3lite/application/handlers/correction.py`
- `backend/services/automation-engine/tests/unit/test_ae3lite_sensor_mode_controller.py`

Работы:

1. В `ensure_active_for_dosing()` применять `stage_keeps_active()`.
2. Для `irrigation_check`, `solution_fill_check`, `prepare_recirculation_check` выполнять no-op, если нет подтверждённой деактивации.
3. Реактивацию после empty window разрешать только при `sample_count=0`, корректной причине и non-persistent stage либо явном inactive state.
4. Не считать повторный idempotent activate безопасной заменой корректной state tracking: он всё равно расходует дедлайн и command bandwidth.

Критерии приёмки:

- обычная последовательность `EC -> observe -> pH -> observe` не публикует sensor activation перед каждой дозой;
- sensor activation выполняется на входе в stage и при подтверждённом recovery case;
- число `CORRECTION_SENSOR_MODE_REACTIVATED` в штатном цикле равно нулю.

### P1. Унифицировать PID reset, dose decision и success deadband

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py`
- `backend/services/automation-engine/ae3lite/application/handlers/base.py`
- `backend/services/automation-engine/tests/unit/test_ae3lite_correction_planner.py`

Работы:

1. Сначала resolve controller config и PID-zone coefficients.
2. Для PID reset использовать тот же resolved deadband, что применяется к `needs_ec`, `needs_ph_*` и success.
3. Recipe `min/max` оставить hard/agronomic bounds и diagnostic context, но не использовать как setpoint success.
4. Сохранить отдельный reset при смене направления pH и смене nutrient component.
5. Проверить `allow_ec`, `allow_ph` и frozen EC: отключённый контур не должен влиять на success/reset.

Обязательные regression cases:

- EC `1.26..1.339` при target `1.4`, deadband `0.06`, recipe tolerance `10%`: PID не сбрасывается и EC correction продолжается;
- EC `1.34..1.46`: success/reset допустимы по симметричному deadband;
- pH внутри recipe range, но вне `±0.04`: correction продолжается;
- overshoot за верхний deadband не считается target reached;
- disabled EC не блокирует pH-only outcome.

### P1. Развести hydraulic duration и correction budget

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/application/use_cases/workflow_router.py`
- `backend/services/automation-engine/ae3lite/application/handlers/irrigation_check.py`
- `backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py`
- Laravel preset validation/UI при изменении смысла полей

Работы:

1. Формально определить:
   - `duration_sec` — максимальное время подачи воды растениям;
   - `correction_slack_sec` — дополнительный bounded budget автомата, не разрешающий бесконтрольное продление полива;
   - `stage_timeout_sec` — hard safety ceiling.
2. Устранить текущую ситуацию, когда наличие requested duration полностью вытесняет `correction_slack_sec` и `stage_timeout_sec`.
3. Не продлевать работу irrigation pump только ради chemistry correction.
4. Если post-irrigation recovery остаётся запрещённой, после hydraulic stop только зафиксировать chemistry outcome и передать решение следующему существующему workflow; не возвращать удалённый `IRRIG_RECIRC`.
5. Проверить worst-case бюджет одной EC и одной pH итерации по pump duration, transport delay, settle и stop reserve.

Критерии приёмки:

- pump работает не дольше запрошенной hydraulic duration;
- hard stage timeout всегда конечен;
- новая доза не начинается, если она не помещается в безопасный остаток correction budget;
- отсутствие времени на сходимость даёт `targets_not_achieved`, а не ложный success.

### P2. Ограничить component-specific EC top-up

Затрагиваемые файлы:

- `backend/services/automation-engine/ae3lite/application/services/correction_pipeline.py`
- `backend/services/automation-engine/ae3lite/application/services/stage_runtime_config.py`
- `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py`
- effective-target/config validation и документация

Работы:

1. Не позволять `calcium` бесконечно закрывать весь full EC gap без component budget.
2. Вычислять допустимый cumulative top-up из recipe/baseline/component targets или вводить fail-closed cap в существующую authority policy.
3. Для большого общего EC deficit рекомендовать существующий prepare/solution workflow вместо calcium-only maintenance.
4. Для test-node выбрать `npk` как generic EC actuator либо явно обозначить calcium-only сценарий как синтетический тест.
5. При исчерпании component budget создавать alert, а не продолжать дозирование до общего max-attempt/deadline.

### P2. Синхронизировать документацию и test-node

Обновить без противоречащих legacy-разделов:

- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md`
- `doc_ai/04_BACKEND_CORE/ae3lite.md`
- `firmware/test_node/README.md`

Работы:

1. Удалить утверждение `irrigation: только pH`, если канон остаётся pH + optional `calcium|npk`.
2. Удалить устаревшее описание `IRRIG_RECIRC`, Ca/Mg/micro и post-irrigation recovery.
3. Зафиксировать различие recipe range, PID deadband и hard bounds.
4. Зафиксировать hydraulic/chemistry outcomes и deadline semantics.
5. Оставить в test-node README единственные актуальные drift-значения.
6. После появления serial-порта прошить собранную test-node firmware и повторить realhw прогон узким YAML-набором по `REALHW_TEST_NODE_AGENT_GUIDE.md`.

## 6. Тестовый план

### Unit

| Область | Сценарии |
|---|---|
| Deadline admission | Команда помещается/не помещается в остаток стадии |
| In-flight reconciliation | `ACK -> DONE` после stage deadline; terminal error; poll timeout |
| Restart recovery | Worker restart между publish, ACK и DONE |
| Target outcome | Achieved, not achieved, stale, unavailable telemetry |
| Sensor mode | Persistent stage no-op; подтверждённая реактивация |
| PID | Recipe range против deadband; overshoot; direction switch; frozen/disabled contour |
| Component budget | calcium/npk cap, exhausted budget, missing policy |

### Integration

1. AE3 command publish/reconcile с History Logger fixture.
2. Полный `irrigation_start -> irrigation_check -> stop -> completed`:
   - targets achieved;
   - targets missed;
   - deadline во время дозы;
   - restart во время дозы.
3. Проверка `ae_commands`, legacy `commands`, `pid_state`, `zone_events`, alerts и terminal task diagnostics.
4. Проверка отсутствия прямого MQTT publish.

### Docker-команды

```bash
docker compose -f backend/docker-compose.dev.yml ps
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q tests/unit/test_ae3lite_correction_planner.py
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q tests/unit/test_ae3lite_correction_handler.py
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q tests/unit/test_ae3lite_sensor_mode_controller.py
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q tests/unit/test_ae3lite_handler_irrigation_check_correction.py
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -q
```

Laravel-тесты добавляются только если меняются terminal diagnostics, presenter, validation или compiled config contract.

### Real hardware

1. Прошить test-node с актуальным drift.
2. Запустить только correction/irrigation realhw scenario через MQTT `1884`, без node-sim.
3. Проверить минимум два цикла:
   - достижение target до дедлайна;
   - недостижение target без dangling command и без ложного `CORRECTION_COMPLETE`.
4. Снять timeline: decision, activation, dose, ACK, DONE, observation, PID update, stop, terminal event.

## 7. Порядок поставки

| Шаг | Содержание | Условие перехода |
|---|---|---|
| 1 | P0 command admission/reconciliation | Нет dangling dose в тестах restart/deadline |
| 2 | P0 target outcome | Miss видим, гидравлический retry не запускается |
| 3 | P1 sensor mode | Нет redundant activation в normal flow |
| 4 | P1 PID deadband | Reset/dose/success используют одну границу |
| 5 | P1 timing semantics | Hydraulic duration не превышается |
| 6 | P2 component cap и docs | Policy fail-closed и документы согласованы |
| 7 | Test-node firmware + realhw | Два последовательных цикла без dangling commands/ложного success |

После каждого runtime-шага необходимо перезапустить только `automation-engine`, проверить `/health/ready` и выполнить один контролируемый цикл зоны 3. Одновременное изменение P0, PID tuning и firmware drift в одном эксперименте запрещено: иначе невозможно атрибутировать результат.

## 8. Rollback и эксплуатационная безопасность

- Перед рестартом убедиться, что нет активной mutating-команды или сохранить её correlation id для recovery.
- При rollback не удалять `ae_commands`, `commands`, `pid_state` или `zone_events`.
- Не выполнять ручной DDL и ручную подстановку terminal status.
- При неизвестном результате дозы считать состояние химии неопределённым: остановить исполнительные механизмы, поднять alert и потребовать свежую телеметрию.
- Не увеличивать `max_dose_ml`, `max_dose_ms`, попытки или correction window до исправления reconciliation и повторной sensor activation.

## 9. Definition of Done

- [ ] Все P0/P1 regression tests зелёные.
- [ ] Полный automation-engine suite зелёный.
- [ ] Новые terminal tasks не оставляют дозирующие `accepted/NULL` команды.
- [ ] `last_dose_at` соответствует последней физически завершённой дозе.
- [ ] pH/EC success определяется PID deadband вокруг setpoint.
- [ ] Target miss имеет event, alert и terminal diagnostics.
- [ ] Hydraulic target miss не вызывает автоматический повторный полив.
- [ ] Persistent stages не выполняют pre-dose sensor reactivation.
- [ ] Fail-closed guards и one-action-per-tick сохранены.
- [ ] Команды продолжают идти исключительно через History Logger.
- [ ] Canonical `doc_ai` и test-node README не противоречат runtime.
- [ ] Realhw-прогон зоны 3 подтверждает отсутствие зависаний и неучтённых доз.

## 10. Связанные документы

- [`doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`](doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md)
- [`doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`](doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md)
- [`doc_ai/06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md`](doc_ai/06_DOMAIN_ZONES_RECIPES/PID_CONFIG_REFERENCE.md)
- [`doc_ai/04_BACKEND_CORE/ae3lite.md`](doc_ai/04_BACKEND_CORE/ae3lite.md)
- [`doc_ai/13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md`](doc_ai/13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
