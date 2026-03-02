# Storage Irrigation Node

Нода накопления и полива (`type=irrig`) с канальным профилем, совместимым с виртуальной IRR-нодой `test_node`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Назначение

- Выполняет команды `set_relay` для 6 IRR-актуаторов (`pump_main`, `valve_*`) с firmware-locked GPIO.
- Поддерживает сервисную команду `state` на канале `storage_state` с `snapshot` для `IRR_STATE_SNAPSHOT`.
- Публикует телеметрию по level-switch каналам 2-бакового контура.
- Публикует `storage_state/event` со `snapshot` (и `state` alias) при событиях заполнения (`clean_fill_completed`, `solution_fill_completed`).
- Работает через `node_framework` с HMAC-проверкой команд (если `allow_legacy_hmac=false`).

## Канонический контракт

- `node_type` в runtime и `node_hello`: `irrig`.
- Канальный профиль: `6 actuator + 4 level-switch`.
- Сервисный channel без GPIO: `storage_state`.
- Основная команда актуатора: `set_relay` с `params.state`.
- Сервисный канал two-tank: `storage_state/state` (возвращает `details.snapshot` + `details.state` + freshness-поля).
- Для `pump_main` действует interlock: включение разрешено только при открытых `valve_clean_supply|valve_solution_supply` и `valve_solution_fill|valve_irrigation`.
- Терминальные статусы: `DONE`/`ERROR`.
- Неизвестная команда: `ERROR` + `error_code=unknown_command`.

## GPIO

### Фиксированные GPIO ноды (ESP32 default)

- `I2C SDA` (INA209 + OLED): `GPIO21`
- `I2C SCL` (INA209 + OLED): `GPIO22`
- `Factory reset button`: `GPIO0` (active-low, hold 20s)

### GPIO каналов IRR

Каналы и GPIO зашиты в прошивке (`main/storage_irrigation_node_channel_map.c`) и не принимаются извне:

- `pump_main` -> `GPIO25`
- `valve_clean_fill` -> `GPIO26`
- `valve_clean_supply` -> `GPIO27`
- `valve_solution_fill` -> `GPIO32`
- `valve_solution_supply` -> `GPIO33`
- `valve_irrigation` -> `GPIO23`
- `level_clean_min` -> `GPIO16`
- `level_clean_max` -> `GPIO17`
- `level_solution_min` -> `GPIO18`
- `level_solution_max` -> `GPIO19`

При получении внешнего `.../config` секция `channels` принудительно заменяется на firmware map.
То же выполняется при старте ноды: сохраненный в NVS `channels` нормализуется к прошивочному набору.

## Публикации MQTT

- `hydro/{gh}/{zone}/{node}/status`
- `hydro/{gh}/{zone}/{node}/heartbeat`
- `hydro/{gh}/{zone}/{node}/{channel}/telemetry`
- `hydro/{gh}/{zone}/{node}/{channel}/command_response`
- `hydro/{gh}/{zone}/{node}/storage_state/event`
- `hydro/{gh}/{zone}/{node}/config_report`
- `hydro/node_hello`

## Ограничения и безопасность

- Очередь команд ноды: `8`.
- Global dedup `cmd_id`: кеш `128`, TTL `5 минут`.
- Для production рекомендуется `allow_legacy_hmac=false` и обязательный `node_secret`.
- `run_pump` сохранён как legacy-команда для совместимости E2E/HIL, но контур two-tank AE должен использовать `set_relay` + `storage_state/state`.

## Файлы

- `main/storage_irrigation_node_app.c`
- `main/storage_irrigation_node_init.c`
- `main/storage_irrigation_node_init_steps.c`
- `main/storage_irrigation_node_framework_integration.c`
- `main/storage_irrigation_node_tasks.c`
- `main/storage_irrigation_node_defaults.h`

## Связанные документы

- `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
- `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `../../../doc_ai/02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
- `../../../configs/nodes/storage_irrigation_node_template.json`
