# TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md
# Матрица соответствия `firmware/test_node` и боевых прошивок нод

**Версия:** 1.0  
**Дата обновления:** 2026-03-02  
**Статус:** Актуально (reference для migration от test-node к real-node)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать точное соответствие между:

- каналами/командами `firmware/test_node`;
- фактическими каналами/командами боевых прошивок (`ph_node`, `ec_node`, `climate_node`, `light_node`, `storage_irrigation_node`, `relay_node`).

Документ нужен для безопасного перевода E2E/HIL сценариев в production-runtime без скрытых несовместимостей.

---

## 2. Источники (код)

- `firmware/test_node/main/test_node_app.c`
- `firmware/nodes/ph_node/main/ph_node_channel_map.c`
- `firmware/nodes/ph_node/main/ph_node_framework_integration.c`
- `firmware/nodes/ec_node/main/ec_node_channel_map.c`
- `firmware/nodes/ec_node/main/ec_node_framework_integration.c`
- `firmware/nodes/climate_node/main/climate_node_framework_integration.c`
- `firmware/nodes/light_node/main/light_node_channel_map.c`
- `firmware/nodes/light_node/main/light_node_framework_integration.c`
- `firmware/nodes/storage_irrigation_node/main/storage_irrigation_node_framework_integration.c`
- `firmware/nodes/relay_node/main/relay_node_hw_map.h`
- `firmware/nodes/relay_node/main/relay_node_framework_integration.c`
- `firmware/nodes/common/components/node_framework/node_command_handler.c`
- `firmware/nodes/common/components/node_framework/node_framework.c`

---

## 3. Легенда совместимости

- `Direct` — можно использовать без переименования и без изменения семантики команды.
- `Alias/Adapter` — нужен слой алиасов/маппинга (имя канала и/или команда).
- `Missing` — в текущих real-node прошивках нет эквивалента; нужна доработка.
- `Partial` — есть частичная поддержка, но поведение отличается от test-node.

---

## 4. Матрица каналов

## 4.1. `nd-test-irrig-1` (`type=irrig`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `pump_main` | `storage_irrigation_node` (`set_relay`) | `Direct` | Production IRR-node поддерживает latched `set_relay {state:true|false}`; interlock `pump_main` остаётся обязательным. |
| `main_pump` (alias) | `storage_irrigation_node` (`pump_main`) | `Alias/Adapter` | Alias есть только в test-node; в real-node нужно канонизировать имя в одном месте. |
| `valve_clean_fill` | `storage_irrigation_node/valve_clean_fill` | `Direct` | Канал реализован в прошивочной карте `storage_irrigation_node`; основной контракт — latched `set_relay`. |
| `valve_clean_supply` | `storage_irrigation_node/valve_clean_supply` | `Direct` | Канал реализован в прошивочной карте `storage_irrigation_node`; основной контракт — latched `set_relay`. |
| `valve_solution_fill` | `storage_irrigation_node/valve_solution_fill` | `Direct` | Канал реализован в прошивочной карте `storage_irrigation_node`; основной контракт — latched `set_relay`. |
| `valve_solution_supply` | `storage_irrigation_node/valve_solution_supply` | `Direct` | Канал реализован в прошивочной карте `storage_irrigation_node`; основной контракт — latched `set_relay`. |
| `valve_irrigation` | `storage_irrigation_node/valve_irrigation` | `Direct` | Канал реализован в прошивочной карте `storage_irrigation_node`; основной контракт — latched `set_relay`. |
| `level_clean_min` | `storage_irrigation_node/level_clean_min` | `Direct` | Реализован как дискретный level-switch канал. |
| `level_clean_max` | `storage_irrigation_node/level_clean_max` | `Direct` | Реализован как дискретный level-switch канал. |
| `level_solution_min` | `storage_irrigation_node/level_solution_min` | `Direct` | Реализован как дискретный level-switch канал. |
| `level_solution_max` | `storage_irrigation_node/level_solution_max` | `Direct` | Реализован как дискретный level-switch канал. |
| `pump_in` (service alias) | `storage_irrigation_node` | `Missing` | Сервисный alias отсутствует; используется канонический набор IRR-каналов. |
| `fill_valve` (service alias) | `relay_node` | `Direct` | Есть в default HW map `relay_node`. |
| `water_control` (service alias) | `relay_node` | `Direct` | Есть в default HW map `relay_node`. |
| `drain_valve` (service alias) | `relay_node` | `Direct` | Есть в default HW map `relay_node`. |
| `drain_main`/`drain_pump`/`drain` | `relay_node` | `Missing` | В default HW map отсутствуют. |
| `pump_irrigation` (service alias) | `storage_irrigation_node` | `Alias/Adapter` | В real-node нужен явный канал в NodeConfig; в test-node это внутренний transient-контур. |
| `pump_bus_current` (service/probe) | `storage_irrigation_node` | `Missing` | В каноническом IRR-профиле `storage_irrigation_node` этот канал не публикуется; используются `level_*` switch-каналы. |
| `water_level` / `flow_present` (service/probe) | отдельная sensor-node / расширение irrig-node | `Missing` | В текущих real-node прошивках нет готового прямого канала с такой семантикой. |
| `storage_state` | `storage_irrigation_node/storage_state` | `Direct` | Реальная IRR-нода публикует `storage_state/event` и обслуживает `storage_state/state` для two-tank runtime. |

Критично:

- `test_node` имеет interlock и staged-сценарии 2-баковой модели; в текущих real-node этого поведения как единого контракта нет.

## 4.2. `nd-test-ph-1` (`type=ph`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `ph_sensor` | `ph_node/ph_sensor` | `Direct` | Канал совпадает. |
| `pump_acid` | `ph_node/ph_doser_down` или `storage_irrigation_node/pump_acid` | `Alias/Adapter` | В коде `ph_node` актуаторы называются `ph_doser_up`/`ph_doser_down`, не `pump_acid`/`pump_base`. |
| `pump_base` | `ph_node/ph_doser_up` или `storage_irrigation_node/pump_base` | `Alias/Adapter` | Нужен явный mapping направлений дозирования. |
| `system` (sensor-mode service) | `ph_node` | `Missing` | Команды `activate/deactivate_sensor_mode` в боевой `ph_node` не зарегистрированы. |

## 4.3. `nd-test-ec-1` (`type=ec`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `ec_sensor` | `ec_node/ec_sensor` | `Direct` | Канал совпадает. |
| `pump_a` | `ec_node/pump_a` | `Direct` | Совпадает по имени и роли. |
| `pump_b` | `ec_node/pump_b` | `Direct` | Совпадает по имени и роли. |
| `pump_c` | `ec_node/pump_c` | `Direct` | Совпадает по имени и роли. |
| `pump_d` | `ec_node/pump_d` | `Direct` | Совпадает по имени и роли. |
| `system` (sensor-mode service) | `ec_node` | `Missing` | Команды `activate/deactivate_sensor_mode` в боевой `ec_node` не зарегистрированы. |

## 4.4. `nd-test-soil-1` (`type=water_sensor`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `soil_moisture` | отдельная soil/water-sensor node | `Missing` | В текущей матрице боевых прошивок нет канонической отдельной `soil`-ноды с тем же runtime-контрактом, поэтому smart-irrigation real-hardware E2E пока привязан к `test_node`. |
| `system` (`set_fault_mode` для soil seed) | real soil-node | `Missing` | Сервисный seed/fault канал специфичен для `test_node`; для боевой soil-ноды нужен другой deterministic harness path. |

## 4.5. `nd-test-climate-1` (`type=climate`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `air_temp_c` | `climate_node/temperature` | `Alias/Adapter` | Нужен rename канала (`air_temp_c -> temperature`). |
| `air_rh` | `climate_node/humidity` | `Alias/Adapter` | Нужен rename канала (`air_rh -> humidity`). |
| `fan_air` | `climate_node` actuator channel из NodeConfig | `Partial` | Поддержка есть через `set_relay`, но только если такой канал реально описан в NodeConfig. |
| `fan` (alias) | `climate_node` actuator channel из NodeConfig | `Alias/Adapter` | Alias присутствует в test-node; в real-node — только если задан канал `fan`. |
| `heater` | `climate_node` actuator channel из NodeConfig | `Partial` | Поддержка через `set_relay` при наличии канала в NodeConfig. |
| `co2` | `climate_node/co2` | `Missing` в test-node | В real-node есть `co2`, а в test-node виртуальной климат-ноде его нет. |

## 4.6. `nd-test-light-1` (`type=light`)

| Канал в test_node | Реальная нода | Совместимость | Детали migration |
|---|---|---|---|
| `light_level` | `light_node/light` | `Alias/Adapter` | Нужен rename (`light_level -> light`). |
| `white_light` | `light_node` | `Missing` | `light_node` сейчас sensor-only (без actuator команд `set_relay/set_pwm`). |

---

## 5. Матрица команд

`test_node` распознаёт расширенный набор команд, включая симуляционные/service-команды.
Боевые ноды работают через `node_command_handler` и локальные регистрации.

| Команда | test_node | Real nodes | Совместимость | Комментарий |
|---|---|---|---|---|
| `test_sensor` | Да | Да (`ph/ec/climate/light`) | `Direct` | Канальные проверки сенсоров в real-node есть. |
| `probe_sensor` | Да | Нет | `Missing` | Требуется alias на `test_sensor` или отдельный handler. |
| `state` | Да | Нет | `Missing` | Нужен отдельный built-in/handler в real-node. |
| `report_config` / `config_report` / `get_config` / `sync_config` | Да | Нет | `Missing` | В real-node как команда не зарегистрировано. |
| `restart` | Да | Да (built-in) | `Direct` | Built-in в `node_command_handler`. |
| `reboot` | Да (alias к restart) | Нет | `Alias/Adapter` | Нужен alias `reboot -> restart` на orchestration слое или в firmware. |
| `set_relay` | Да | Да (`relay_node`, `climate_node`) | `Partial` | В `ph/ec/pump/light` как команда отсутствует. |
| `set_pwm` | Да | Да (`climate_node`) | `Partial` | Для `light_node` команда отсутствует. |
| `run_pump` | Да | Да (`ph/ec/pump`) | `Direct` | Основная pump-команда для боевых нод. |
| `dose` | Да | Нет | `Missing` | Нужен adapter `dose -> run_pump(duration_ms|ml->ms)` или firmware support. |
| `emit_event` | Да | Нет | `Missing` | Специфично для test-node. |
| `set_fault_mode` | Да | Нет | `Missing` | Симуляционная команда test-node. |
| `reset_state` | Да | Нет | `Missing` | Симуляционная команда test-node. |
| `reset_binding` | Да | Нет | `Missing` | Симуляционная/операционная команда test-node. |
| `activate_sensor_mode` | Да | Нет | `Missing` | В real `ph/ec` не зарегистрировано. |
| `deactivate_sensor_mode` | Да | Нет | `Missing` | В real `ph/ec` не зарегистрировано. |
| `calibrate` | Нет (в test_node) | Да (`ph/ec`) | `Gap in test-node` | Для parity e2e желательно поддержать и в test-node. |
| `calibrate_ph` | Нет (в test_node) | Да (`ph`) | `Gap in test-node` | Аналогично. |
| `calibrate_ec` | Нет (в test_node) | Да (`ec`) | `Gap in test-node` | Аналогично. |
| `set_time` | Нет (в test_node) | Да (built-in) | `Gap in test-node` | В real-node обязательный built-in для time sync pipeline. |
| `exit_safe_mode` | Нет (в test_node) | Да (framework) | `Gap in test-node` | Built-in framework. |

---

## 6. Security/Envelope различия (критично)

`test_node`:

- принимает только canonical поля (`cmd_id/cmd/params/ts/sig`);
- `sig` проверяется только по формату `hex64`.

Real-node (`node_command_handler`):

- требует HMAC-подпись (`ts` + `sig`), пока в NodeConfig включена строгая проверка команд (см. `NODE_CONFIG_SPEC.md`);
- проверяет timestamp и подпись;
- при неизвестной команде возвращает `ERROR/unknown_command`.

Следствие:

- команда, проходящая в test-node, может быть отклонена боевой нодой по `hmac_required`, `invalid_signature`, `time_not_synced`, `timestamp_expired`.

---

## 7. Обязательные шаги перед production rollout

1. Нормализовать канальные имена между test и real (`air_temp_c->temperature`, `air_rh->humidity`, `light_level->light`, `pump_acid/pump_base <-> ph_doser_*`).
2. Зафиксировать adapter для команд (`dose->run_pump`, `reboot->restart`, опционально `probe_sensor->test_sensor`).
3. Определить источник и контракт для `level_*` и `storage_state` (отдельная real-node или расширение existing firmware).
4. Добавить/согласовать `activate_sensor_mode/deactivate_sensor_mode` в `ph/ec` либо убрать зависимость orchestration от этих команд.
5. Для strict e2e на real hardware использовать HMAC-подписанные команды и синхронизацию времени до старта циклов.

---

## 8. Ссылки

- `doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
