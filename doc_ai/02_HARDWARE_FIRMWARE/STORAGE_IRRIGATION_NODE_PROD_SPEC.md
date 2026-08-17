# STORAGE_IRRIGATION_NODE_PROD_SPEC.md
# Production-спецификация ноды накопления и полива (`storage_irrigation_node`)

**Версия:** 1.4
**Дата обновления:** 2026-08-17 (irrigation-active = клапаны; auto-arm `irrigation` stage-guard; `run_pump` на `pump_main`)
**Статус:** Актуально

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать прод-контракт для прошивки `firmware/nodes/storage_irrigation_node`:

- каналы и команды;
- MQTT-топики;
- режимы работы;
- GPIO-профиль;
- ограничения и обязательные проверки перед rollout.

---

## 2. Идентичность ноды

- `firmware_module`: `storage_irrigation_node`
- `node_type` (канонический): `irrig`
- дефолтный `node_id`: `nd-irrig-1`
- `node_hello.node_type`: `irrig`

Важно:
- `storage_irrigation_node` используется только как имя прошивочного модуля;
- в payload/БД должен использоваться только канонический `type=irrig`.

---

## 3. Каналы и команды

## 3.1. Поддерживаемые каналы

- `pump_main` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO13`)
- `valve_clean_fill` (`ACTUATOR`, `actuator_type=VALVE`, `GPIO12`)
- `valve_clean_supply` (`ACTUATOR`, `actuator_type=VALVE`, `GPIO14`)
- `valve_solution_fill` (`ACTUATOR`, `actuator_type=VALVE`, `GPIO27`)
- `valve_solution_supply` (`ACTUATOR`, `actuator_type=VALVE`, `GPIO26`)
- `valve_irrigation` (`ACTUATOR`, `actuator_type=VALVE`, `GPIO25`)
- `level_clean_min` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO33`)
- `level_clean_max` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO32`)
- `level_solution_min` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO35`)
- `level_solution_max` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO34`)
- сервисный командный канал `storage_state` (`ACTUATOR`, `actuator_type=SYSTEM`, без GPIO;
  только `state`/`event`, не физический актуатор)

Вне текущего firmware map:
- `valve_drain` — **не реализован** на production `storage_irrigation_node` (нет GPIO в HW-карте).
  AE3 `solution_change` / `solution_drain_*` требуют этот канал и fail-closed с
  `solution_change_drain_channel_missing`, пока канал не появится на irrig-ноде
  (есть в `test_node` для HIL).

Для всех 4 `level_*` датчиков:
- логика входа: ожидается подтяжка к `VCC` (`pull-up`);
- геркон замкнут при нижнем положении поплавка (воды нет) и замыкает вход на `GND`;
- при наполнении поплавок поднимается, геркон размыкается, вход уходит в `HIGH`;
- активное состояние `WATER_LEVEL_SWITCH=1` означает «уровень достигнут / вода есть» и определяется по `HIGH` (`active_low=false`);
- **GPIO34 / GPIO35** (`level_solution_max` / `level_solution_min`) на классическом ESP32 —
  input-only без внутренних pull-up/pull-down: **обязательны внешние pull-up** на плате
  (программный `pull-up` в firmware map их не обеспечивает).

Сервисный канал `storage_state`:
- `type=ACTUATOR`, `actuator_type=SYSTEM` — firmware-locked service channel без GPIO;
- используется только для `cmd=state` и публикации `storage_state/event`;
- `SYSTEM` — irrig service channel (firmware `storage_irrigation_node_config.c`);
  перечислен в общем `actuator_type` в `NODE_CONFIG_SPEC.md`.

## 3.2. Поддерживаемые команды

- `set_relay` (канальный, для всех 6 actuator-каналов IRR профиля)
- `run_pump` (только `pump_main`; обёртка над `set_relay {state:true, duration_ms}` — см. `storage_irrigation_fw_commands.c`)
- `test_sensor` (только `level_*` WATER_LEVEL_SWITCH каналы; возвращает текущий `value`/`raw`)
- `probe_sensor` (alias `test_sensor` на тех же `level_*` каналах)
- `state` (только на сервисном канале `storage_state`, возвращает `snapshot/state` для two-tank guard)
- built-in через `node_command_handler`: `set_time`, `restart`

Ожидаемая модель ответа:
- `state`: immediate terminal `DONE`/`ERROR`.
- `set_relay` (latched ON/OFF, без `duration_ms`): immediate terminal `DONE`/`ERROR`.
- `set_relay {state:true, duration_ms}` для diagnostic/test path отвечает `ACK`, удерживает канал включённым
  `duration_ms`, затем нода обязана локально вернуть канал в `OFF` и отправить terminal `DONE`
  по тому же `cmd_id`.
- специальный dry-run path для `pump_main`: `set_relay {state:true, duration_ms<=3000}` допускается
  без открытого flow path и должен использоваться только для ручного smoke/test;
- `pump_main/set_relay {state:true, timeout_ms, stage}` (stage-arm): immediate terminal `DONE`
  (AE3 ждёт `DONE`; `complete_on_ack` deprecated). Guard остаётся armed после ответа.
  Повторный terminal по тому же arm-`cmd_id` при fail-safe stop / stage-timeout **не** публикуется;
  исход stage передаётся через `storage_state/event`.
  Явный `pump_main OFF` (другой `cmd_id`) снимает guard и может дополнительно опубликовать
  `DONE` для arm-`cmd_id` с `details.reason_code=stage_stopped_by_command`.

Дополнительные правила:
- `set_relay {state:true}` для actuator-каналов IRR-профиля работает как latched `ON/OFF` semantics:
  канал остаётся включенным до явной команды `set_relay {state:false}`;
- если для actuator-команды явно передан `duration_ms`, latched-семантика заменяется transient test-mode:
  канал обязан автоматически вернуться в `OFF` и завершить исходный `cmd_id` terminal-ответом;
- `pump_main/set_relay {state:true, timeout_ms, stage}` поддерживается для
  `stage in {"solution_fill", "prepare_recirculation", "irrigation"}` и arm'ит локальный stage-guard;
- irrigation path без явного `timeout_ms/stage`: открытие `valve_irrigation` auto-arm'ит guard на
  `fail_safe_guards.irrigation_timeout_ms` (default 600000). Последующий `run_pump` **не укорачивает**
  уже взведённый потолок. `run_pump` DONE гасит только насос; клапаны держит guard до timeout или `irrigation_stop`.
- `is_irrigation_active` = `valve_solution_supply && valve_irrigation` (насос не обязателен);
- dry-run `pump_main/set_relay {state:true, duration_ms<=3000}` является единственным разрешённым bypass
  interlock для ручного теста "на сухую"; любой другой `pump_main ON` без flow path остаётся запрещён;
- по истечении `timeout_ms` нода обязана локально остановить весь соответствующий flow-path,
  снять stage-guard и опубликовать `storage_state/event`
  (`solution_fill_timeout`, `prepare_recirculation_timeout` или `irrigation_timeout`) **без** второго terminal
  `ERROR`/`DONE` по arm-`cmd_id` (arm уже завершён immediate `DONE`);
- interlock `pump_main`: включение запрещено без открытых supply-клапанов (`valve_clean_supply|valve_solution_supply`)
  и target-клапанов (`valve_solution_fill|valve_irrigation`);
- при попытке нарушения interlock возвращается `ERROR` + `error_code=pump_interlock_blocked`;
- `level_clean_max` локально завершает только `clean_fill` (`valve_clean_fill -> OFF`) и публикует `clean_fill_completed`
  один раз на эпизод `clean_fill`;
- для `clean_fill` проверка `level_clean_min` по `clean_fill_min_check_delay_ms` **не применяется**:
  клапан остаётся открытым, пока уровень не достигнет `level_clean_max`; пустой источник определяется
  через AE3 timeout/retry;
- после `solution_fill_clean_min_check_delay_ms` нода проверяет `level_clean_min` на каждом fail-safe scan до terminal event; если датчик `0`,
  локально завершает `solution_fill`
  (`pump_main/valve_solution_fill/valve_clean_supply -> OFF`) и публикует `solution_fill_source_empty`;
- после `solution_fill_solution_min_check_delay_ms` нода проверяет `level_solution_min` на каждом fail-safe scan до terminal event; если датчик `0`,
  локально завершает `solution_fill`
  (`pump_main/valve_solution_fill/valve_clean_supply -> OFF`) и публикует `solution_fill_leak_detected`;
- `level_solution_max` локально завершает `solution_fill`
  (`pump_main/valve_solution_fill/valve_clean_supply -> OFF`) и публикует `solution_fill_completed`
  один раз на эпизод `solution_fill`;
- при включённом `recirculation_solution_min_guard_enabled` нода завершает `prepare_recirculation`
  по `level_solution_min=0` с событием `recirculation_solution_low`;
- при включённом `irrigation_solution_min_guard_enabled` нода завершает `irrigation`
  по `level_solution_min=0` с событием `irrigation_solution_low`;
- отдельная физическая кнопка `E-Stop` на `GPIO15` (active-low, pull-up) пока удерживается в нажатом состоянии
  принудительно выключает все 6 актуаторов и отклоняет MQTT `set_relay {state:true}` с
  `ERROR estop_active`; `set_relay {state:false}` остаётся разрешённым как fail-safe stop.
  На нажатие нода публикует `emergency_stop_activated`, на отпускание локально восстанавливает
  предыдущий снимок actuator-состояний.
  **Hardware caveat:** `GPIO15` — strapping pin ESP32; если E-Stop зажат (вход в `LOW`) в момент
  power-on/reset, возможен сбой/нестандартный boot — не держать E-Stop нажатым при старте;
- firmware terminal stop path (`clean_fill_completed`, `solution_fill_*`, `prepare_recirculation`,
  `irrigation`) снимает активный stage-timeout guard соответствующего stage, чтобы уже завершённый
  stage не породил поздний ложный timeout-event;
- каждый `level_*` канал дополнительно публикует `.../{channel}/event` с
  `event_code=level_switch_changed`, полями `channel`, `state`, `initial` и полным `snapshot`;
- channel-level событие отправляется на оба фронта (`0 -> 1`, `1 -> 0`) после debounce-подтверждения;
- после boot/reconnect нода повторно публикует initial-state событие по каждому `level_*` каналу
  после завершения time sync.

Неизвестная команда:
- `ERROR` + `error_code=unknown_command`.

---

## 4. MQTT топики

Нода использует namespace:

`hydro/{gh}/{zone}/{node}/{channel}/{message_type}`

Фактические публикации:

- `.../{channel}/telemetry`
- `.../{level_channel}/event`
- `.../{channel}/command_response`
- `.../diagnostics`
- `.../storage_state/event`
- `.../status`
- `.../heartbeat`
- `.../config_report`
- `hydro/node_hello`

Дополнительно для production IRR-ноды:
- `.../diagnostics` используется для structured engineering snapshots, которые не соответствуют scalar telemetry contract;
- snapshot `diagnostic_type=pump_health` публикует состояние pump channels и INA209;
- `pump_health` не должен публиковаться как `.../pump_health/telemetry`, потому что payload содержит массивы/объекты и не совместим с ingest telemetry.

Фактические подписки:

- `.../{channel}/command`
- `.../config`

---

## 5. GPIO профиль

## 5.1. Фиксированные GPIO

- I2C SDA: `GPIO21`
- I2C SCL: `GPIO22`
- Factory reset button: `GPIO0` (active-low)
- E-Stop button: `GPIO15` (active-low, pull-up; strapping pin — см. §3.1)

Примечание:
- `GPIO21/22` используются для INA209 и OLED;
- эти линии не должны одновременно использоваться как насосные GPIO;
- `GPIO34`/`GPIO35` требуют внешние pull-up на классическом ESP32 (см. §3.1).

## 5.2. Каналы/GPIO зашиты в прошивке

Каналы и GPIO задаются только в firmware map:

- `main/storage_irrigation_node_config.h`
- `main/storage_irrigation_node_config.c`

Внешний `.../config` не может изменить `channels/gpio`:

- при обработке MQTT-конфига `channels` удаляются и заменяются на прошивочный набор;
- при старте ноды сохраненный в NVS `channels` принудительно нормализуется к прошивочному набору.

Runtime-валидация `pump_driver` сохраняется:
- принимаются только `GPIO_IS_VALID_OUTPUT_GPIO(...)`;
- дублирующиеся GPIO для насосных каналов отклоняются.

Top-level секция `fail_safe_guards` допускается и используется как firmware mirror:

```json
{
  "fail_safe_guards": {
    "clean_fill_min_check_delay_ms": 5000,
    "solution_fill_clean_min_check_delay_ms": 5000,
    "solution_fill_solution_min_check_delay_ms": 60000,
    "recirculation_solution_min_guard_enabled": true,
    "irrigation_solution_min_guard_enabled": true,
    "estop_debounce_ms": 80
  }
}
```

Источник истины для frontend/AE3:
- `zone.logic_profile.active_profile.subsystems.diagnostics.execution.fail_safe_guards`

Mirror в NodeConfig:
- `recirculation_stop_on_solution_min` -> `recirculation_solution_min_guard_enabled`
- `irrigation_stop_on_solution_min` -> `irrigation_solution_min_guard_enabled`
- `clean_fill_min_check_delay_ms` deprecated: поле сохраняется в mirror для совместимости, но
  `clean_fill` min-guard в прошивке не применяется.

---

## 6. Режимы работы

- `configured`: рабочий namespace из NVS;
- setup/provisioning: AP-портал (`node_type_prefix=IRRIG`) при отсутствии валидного Wi-Fi/MQTT.

При MQTT reconnect нода:
- подписывается на `hydro/time/response`;
- запрашивает время (`hydro/time/request`);
- публикует `config_report`;
- при temp/unbound конфиге публикует `node_hello`.

До получения `hydro/time/response` нода не публикует `telemetry`, `status`,
`.../{level_channel}/event` и `storage_state/event` с полем `ts`.

---

## 7. Ограничения

- Каналы и GPIO ноды остаются firmware-locked; внешние `config.channels` не принимаются.
- Рабочий two-tank fill/recirc использует latched `set_relay` + `storage_state/state`.
  Штатный AE3 `irrigation_start` — latched клапаны + `pump_main/run_pump {duration_ms}`.
- Stage-level timeout для `solution_fill` и `prepare_recirculation` приходит из backend в
  `pump_main/set_relay` через `params.timeout_ms` и исполняется локальным guard'ом ноды.
  Для `irrigation` guard также auto-arm'ится локально на `irrigation_timeout_ms` при latched клапанах.
- Очередь команд ноды: `8`.
- Global dedup `cmd_id`: кеш `128`, TTL `5 минут`.
- Для production обязательны `node_secret` и строгая HMAC-проверка команд (без ослабления совместимости в NodeConfig; см. `NODE_CONFIG_SPEC.md`).
- `safe_limits.max_duration_ms` остаётся частью firmware map и timed-path в `pump_driver`, но не должен
  использоваться как auto-stop для `set_relay` в production `storage_irrigation_node`.
- `fail_safe_guards` может обновляться с фронта через `zone.logic_profile`, после чего backend обязан
  пересобрать `NodeConfig` IRR-ноды и репаблишить новый mirror в ноду.

---

## 8. Минимальный прод-чеклист

1. `NodeConfig.type == "irrig"`.
2. Прошивочная карта каналов соответствует монтажу: `6 actuator + 4 level-switch` (как в разделе 3.1).
3. Нет конфликта GPIO с `21/22/0`.
4. Для каждого actuator-канала определены `safe_limits.max_duration_ms` и `safe_limits.min_off_ms` в firmware map.
5. Команды проходят по защищённому пути:
   `Laravel scheduler-dispatch -> Automation-Engine -> History-Logger -> MQTT -> Node`.
6. HMAC-валидация включена (обход проверки не допускается).
7. Проверены контракты two-tank:
   `set_relay`, `storage_state/state`, `storage_state/event`, interlock `pump_main`.
8. HIL-проверка пройдена: terminal `DONE/ERROR`, стабильная telemetry, корректный recover после reconnect.

---

## 9. Связанные документы

- `NODE_ARCH_FULL.md`
- `NODE_CHANNELS_REFERENCE.md`
- `NODE_CONFIG_SPEC.md`
- `TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md`
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `../../firmware/nodes/storage_irrigation_node/README.md`
