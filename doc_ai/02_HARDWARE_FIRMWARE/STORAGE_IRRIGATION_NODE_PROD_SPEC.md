# STORAGE_IRRIGATION_NODE_PROD_SPEC.md
# Production-спецификация ноды накопления и полива (`storage_irrigation_node`)

**Версия:** 1.1  
**Дата обновления:** 2026-03-02  
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

- `pump_main` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO25`)
- `valve_clean_fill` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO26`)
- `valve_clean_supply` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO27`)
- `valve_solution_fill` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO32`)
- `valve_solution_supply` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO33`)
- `valve_irrigation` (`ACTUATOR`, `actuator_type=PUMP`, `GPIO23`)
- `level_clean_min` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO16`)
- `level_clean_max` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO17`)
- `level_solution_min` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO18`)
- `level_solution_max` (`SENSOR`, `metric_type=WATER_LEVEL_SWITCH`, `GPIO19`)
- сервисный командный канал `storage_state` (без отдельного GPIO, для `state`/`event`)

## 3.2. Поддерживаемые команды

- `set_relay` (канальный, для всех 6 actuator-каналов IRR профиля)
- `state` (только на сервисном канале `storage_state`, возвращает `snapshot/state` для two-tank guard)
- `run_pump` (legacy-совместимость для E2E/HIL сценариев)
- built-in через `node_command_handler`: `set_time`, `restart`

Ожидаемая модель ответа:
- `set_relay` и `state`: immediate terminal `DONE`/`ERROR`;
- `run_pump`: `ACK` -> terminal `DONE`/`ERROR`.

Дополнительные правила:
- interlock `pump_main`: включение запрещено без открытых supply-клапанов (`valve_clean_supply|valve_solution_supply`)
  и target-клапанов (`valve_solution_fill|valve_irrigation`);
- при попытке нарушения interlock возвращается `ERROR` + `error_code=pump_interlock_blocked`;
- автособытия по достижению max-level:
  `clean_fill_completed`, `solution_fill_completed` в `storage_state/event` со snapshot.

Неизвестная команда:
- `ERROR` + `error_code=unknown_command`.

---

## 4. MQTT топики

Нода использует namespace:

`hydro/{gh}/{zone}/{node}/{channel}/{message_type}`

Фактические публикации:

- `.../{channel}/telemetry`
- `.../{channel}/command_response`
- `.../storage_state/event`
- `.../status`
- `.../heartbeat`
- `.../config_report`
- `hydro/node_hello`

Фактические подписки:

- `.../{channel}/command`
- `.../config`

---

## 5. GPIO профиль

## 5.1. Фиксированные GPIO

- I2C SDA: `GPIO21`
- I2C SCL: `GPIO22`
- Factory reset button: `GPIO0` (active-low)

Примечание:
- `GPIO21/22` используются для INA209 и OLED;
- эти линии не должны одновременно использоваться как насосные GPIO.

## 5.2. Каналы/GPIO зашиты в прошивке

Каналы и GPIO задаются только в firmware map:

- `main/storage_irrigation_node_defaults.h`
- `main/storage_irrigation_node_channel_map.c`

Внешний `.../config` не может изменить `channels/gpio`:

- при обработке MQTT-конфига `channels` удаляются и заменяются на прошивочный набор;
- при старте ноды сохраненный в NVS `channels` принудительно нормализуется к прошивочному набору.

Runtime-валидация `pump_driver` сохраняется:
- принимаются только `GPIO_IS_VALID_OUTPUT_GPIO(...)`;
- дублирующиеся GPIO для насосных каналов отклоняются.

---

## 6. Режимы работы

- `configured`: рабочий namespace из NVS;
- setup/provisioning: AP-портал (`node_type_prefix=IRRIG`) при отсутствии валидного Wi-Fi/MQTT.

При MQTT reconnect нода:
- запрашивает время (`hydro/time/request`);
- публикует `config_report`;
- при temp/unbound конфиге публикует `node_hello`.

---

## 7. Ограничения

- Каналы и GPIO ноды остаются firmware-locked; внешние `config.channels` не принимаются.
- Рабочий two-tank runtime использует `set_relay` + `storage_state/state`.
- `run_pump` оставлен только как legacy совместимость.
- Очередь команд ноды: `8`.
- Global dedup `cmd_id`: кеш `128`, TTL `5 минут`.
- Для production обязательны `node_secret` и `allow_legacy_hmac=false`.

---

## 8. Минимальный прод-чеклист

1. `NodeConfig.type == "irrig"`.
2. Прошивочная карта каналов соответствует монтажу: `6 actuator + 4 level-switch` (как в разделе 3.1).
3. Нет конфликта GPIO с `21/22/0`.
4. Для каждого actuator-канала определены `safe_limits.max_duration_ms` и `safe_limits.min_off_ms` в firmware map.
5. Команды проходят по защищённому пути:
   `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> Node`.
6. HMAC-валидация включена (без legacy bypass).
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
