# Storage Irrigation Node

Нода накопления и полива (`type=irrig`) для production two-tank runtime.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Назначение

- Выполняет команды `set_relay` для 6 IRR-актуаторов (`pump_main`, `valve_*`) с firmware-locked GPIO.
- Поддерживает сервисную команду `state` на канале `storage_state` с `snapshot` для `IRR_STATE_SNAPSHOT`.
- Публикует телеметрию по level-switch каналам 2-бакового контура.
- Публикует structured diagnostics snapshot `pump_health` в `hydro/{gh}/{zone}/{node}/diagnostics`.
- Публикует `storage_state/event` со `snapshot` (и `state` alias) при событиях fail-safe и заполнения:
  `clean_fill_source_empty`, `clean_fill_completed`, `solution_fill_source_empty`,
  `solution_fill_leak_detected`, `solution_fill_completed`, `recirculation_solution_low`,
  `irrigation_solution_low`, `solution_fill_timeout`, `prepare_recirculation_timeout`,
  `emergency_stop_activated`.
- Публикует `.../{level_*}/event` с `event_code=level_switch_changed`, `channel`, `state`, `initial`, `snapshot` сразу после подтверждённого изменения датчика и один раз после boot/reconnect.
- Работает через `node_framework` с HMAC-проверкой команд (строгий режим по умолчанию; см. `../../NODE_CONFIG_SPEC.md`).

## Канонический контракт

- `node_type` в runtime и `node_hello`: `irrig`.
- Канальный профиль: `6 actuator + 4 level-switch`.
- Сервисный channel без GPIO: `storage_state`.
- Основная команда актуатора: `set_relay` с `params.state`.
- Сервисный канал two-tank: `storage_state/state` (возвращает `details.snapshot` + `details.state` + freshness-поля).
- `set_relay {state:true}` на production IRR-ноде работает как latched `ON` и держит канал включенным до явного `set_relay {state:false}`.
- `pump_main/set_relay {state:true, timeout_ms, stage}` arm'ит локальный stage-timeout guard для `solution_fill` или `prepare_recirculation`, отвечает `ACK`, а terminal `DONE/ERROR` публикует позже по тому же `cmd_id`.
- Для `pump_main` действует interlock: включение разрешено только при открытых `valve_clean_supply|valve_solution_supply` и `valve_solution_fill|valve_irrigation`.
- Встроенные fail-safe guards работают локально:
  - `clean_fill`: через `clean_fill_min_check_delay_ms` проверяется `level_clean_min`; при `0` нода выключает `valve_clean_fill` и публикует `clean_fill_source_empty`; при `level_clean_max=1` выключает `valve_clean_fill` и публикует `clean_fill_completed`.
  - `solution_fill`: через `solution_fill_clean_min_check_delay_ms` проверяется `level_clean_min`; при `0` нода выключает `pump_main + valve_clean_supply + valve_solution_fill` и публикует `solution_fill_source_empty`; через `solution_fill_solution_min_check_delay_ms` проверяется `level_solution_min`; при `0` нода выключает тот же path и публикует `solution_fill_leak_detected`; при `level_solution_max=1` нода выключает тот же path и публикует `solution_fill_completed`.
  - `prepare_recirculation`: при включённом `recirculation_solution_min_guard_enabled` нода следит за `level_solution_min`; при `0` выключает `pump_main + valve_solution_fill + valve_solution_supply` и публикует `recirculation_solution_low`.
  - `irrigation`: при включённом `irrigation_solution_min_guard_enabled` нода следит за `level_solution_min`; при `0` выключает `pump_main + valve_solution_supply + valve_irrigation` и публикует `irrigation_solution_low`.
- Каждый `level_*` канал дополнительно публикует собственный MQTT event на оба перехода (`0 -> 1`, `1 -> 0`) после debounce; первая публикация после boot/reconnect помечается `initial=true`.
- На `GPIO23` закреплена отдельная физическая кнопка `E-Stop` (`active_low`, `pull-up`): пока кнопка нажата, нода принудительно выключает все актуаторы и публикует `emergency_stop_activated`; после отпускания нода восстанавливает снимок состояний, который был до нажатия.
- Терминальные статусы: `DONE`/`ERROR`; timed-start использует `ACK -> DONE/ERROR`.
- Неизвестная команда: `ERROR` + `error_code=unknown_command`.

## GPIO

### Фиксированные GPIO ноды (ESP32 default)

- `I2C SDA` (INA209 + OLED): `GPIO21`
- `I2C SCL` (INA209 + OLED): `GPIO22`
- `Factory reset button`: `GPIO0` (active-low, hold 10s)
- `E-Stop button`: `GPIO23` (active-low, pull-up)

### GPIO каналов IRR

Каналы, GPIO и default-параметры зашиты в прошивке (`main/storage_irrigation_node_config.c`) и не принимаются извне:

- `pump_main` -> `GPIO25`
- `valve_clean_fill` -> `GPIO26`
- `valve_clean_supply` -> `GPIO27`
- `valve_solution_fill` -> `GPIO32`
- `valve_solution_supply` -> `GPIO33`
- `valve_irrigation` -> `GPIO14`
- `level_clean_min` -> `GPIO16`
- `level_clean_max` -> `GPIO17`
- `level_solution_min` -> `GPIO18`
- `level_solution_max` -> `GPIO19`

Логика level-switch:
- входы подтянуты к `VCC` (`pull-up`)
- активное состояние датчика: `LOW` (`active_low=true`)

При получении внешнего `.../config` секция `channels` принудительно заменяется на firmware map.
То же выполняется при старте ноды: сохраненный в NVS `channels` нормализуется к прошивочному набору.

Дополнительно нода принимает top-level секцию `fail_safe_guards`:

```json
{
  "fail_safe_guards": {
    "clean_fill_min_check_delay_ms": 5000,
    "solution_fill_clean_min_check_delay_ms": 5000,
    "solution_fill_solution_min_check_delay_ms": 15000,
    "recirculation_solution_min_guard_enabled": true,
    "irrigation_solution_min_guard_enabled": true,
    "estop_debounce_ms": 80
  }
}
```

Эта секция является firmware mirror для frontend/AE3-настроек из
`zone.logic_profile.active_profile.subsystems.diagnostics.execution.fail_safe_guards`.

## Публикации MQTT

- `hydro/{gh}/{zone}/{node}/status`
- `hydro/{gh}/{zone}/{node}/heartbeat`
- `hydro/{gh}/{zone}/{node}/{channel}/telemetry`
- `hydro/{gh}/{zone}/{node}/{level_channel}/event`
- `hydro/{gh}/{zone}/{node}/{channel}/command_response`
- `hydro/{gh}/{zone}/{node}/diagnostics`
- `hydro/{gh}/{zone}/{node}/storage_state/event`
- `hydro/{gh}/{zone}/{node}/config_report`
- `hydro/node_hello`

## Ограничения и безопасность

- Очередь команд ноды: `8`.
- Для production: обязательный `node_secret` и включённая строгая проверка HMAC (см. `../../NODE_CONFIG_SPEC.md`).

## Файлы

- `main/storage_irrigation_node_app.c`
- `main/storage_irrigation_node_init.c`
- `main/storage_irrigation_node_init_steps.c`
- `main/storage_irrigation_node_framework_integration.c`
- `main/storage_irrigation_node_tasks.c`
- `main/storage_irrigation_node_config.h`
- `main/storage_irrigation_node_config.c`

## Связанные документы

- `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
- `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `../../../doc_ai/02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
- `../../../configs/nodes/storage_irrigation_node_template.json`
