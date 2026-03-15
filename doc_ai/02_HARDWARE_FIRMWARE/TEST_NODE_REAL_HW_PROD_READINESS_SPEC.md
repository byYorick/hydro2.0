# TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md
# Спецификация test_node для доведения реальных нод до боевого режима

**Версия:** 1.0  
**Дата обновления:** 2026-03-04  
**Статус:** Актуально (источник истины для `firmware/test_node`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель документа

Зафиксировать фактическое поведение `firmware/test_node` как эталон для:

- HIL/E2E прогонов на реальном железе;
- проверки end-to-end контракта `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel`;
- доведения реальных боевых нод до совместимого runtime-поведения.

Документ основан на фактической реализации:

- `firmware/test_node/main/test_node_app.c`
- `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`
- `firmware/nodes/common/components/config_storage/include/config_storage.h`

---

## 2. Модель узла

Один ESP32 (`test_node`) эмулирует 5 виртуальных нод:

1. `nd-test-irrig-1` (`type=irrig`)
2. `nd-test-ph-1` (`type=ph`)
3. `nd-test-ec-1` (`type=ec`)
4. `nd-test-climate-1` (`type=climate`)
5. `nd-test-light-1` (`type=light`)

### 2.1. Каналы из `config_report`

`nd-test-irrig-1`:
- `pump_main`
- `valve_clean_fill`
- `valve_clean_supply`
- `valve_solution_fill`
- `valve_solution_supply`
- `valve_irrigation`
- `level_clean_min`
- `level_clean_max`
- `level_solution_min`
- `level_solution_max`

`nd-test-ph-1`:
- `ph_sensor`
- `pump_acid`
- `pump_base`
- `system` (service-channel для sensor-mode)

`nd-test-ec-1`:
- `ec_sensor`
- `pump_a`
- `pump_b`
- `pump_c`
- `pump_d`
- `system` (service-channel для sensor-mode)

`nd-test-climate-1`:
- `air_temp_c`
- `air_rh`
- `fan_air`
- `fan` (alias)
- `heater`

`nd-test-light-1`:
- `light_level`
- `white_light`

### 2.2. Служебные/alias каналы, не отражаемые в `config_report`

Реализация дополнительно обрабатывает:

- `storage_state` (service/event)
- `main_pump` (alias `pump_main`)
- `pump_in`, `fill_valve`, `water_control` (fill-alias)
- `drain_main`, `drain_valve`, `drain_pump`, `drain` (drain-alias)
- `pump_irrigation` (внутренняя модель transient)
- `water_level`, `flow_present`, `pump_bus_current` (доступны в `probe_sensor/state`, но не публикуются в periodic telemetry)

Для production-нод это зона риска (см. раздел 8).

---

## 3. MQTT-контракт test_node

## 3.1. Подписки

Через raw wildcard подписки:

- `hydro/+/+/+/+/command` (QoS 1)
- `hydro/+/+/+/config` (QoS 1)

Дополнительно через `mqtt_manager`:

- `hydro/{gh}/{zone}/{node}/config`
- `hydro/{gh}/{zone}/{node}/+/command`
- `hydro/time/response`
- temp fallback:
  - `hydro/gh-temp/zn-temp/{hardware_id}/config`
  - `hydro/gh-temp/zn-temp/{hardware_id}/+/command`

## 3.2. Публикации

Node-level:

- `hydro/{gh}/{zone}/{node}/status` (QoS 1, retain=true)
- `hydro/{gh}/{zone}/{node}/heartbeat` (QoS 1, retain=false)
- `hydro/{gh}/{zone}/{node}/config_report` (QoS 1, retain=false)
- `hydro/{gh}/{zone}/{node}/lwt` (через MQTT Last Will, payload `"offline"`)

Channel-level:

- `hydro/{gh}/{zone}/{node}/{channel}/telemetry`
- `hydro/{gh}/{zone}/{node}/{channel}/command_response`
- `hydro/{gh}/{zone}/{node}/storage_state/event`

Системный:

- `hydro/node_hello`

## 3.3. QoS/retain (фактически)

- `telemetry`: QoS 1, retain=false
- `command_response`: QoS 1, retain=false
- `status`: QoS 1, retain=true
- `heartbeat`: QoS 1, retain=false
- `config_report`: QoS 1, retain=false
- `node_hello`: QoS 1, retain=false

---

## 4. Контракт команд

## 4.1. Входной payload (строгая валидация)

Допускаются только поля:

- `cmd_id` (string, non-empty)
- `cmd` (string, non-empty)
- `params` (object)
- `ts` (integer >= 0)
- `sig` (hex string length=64)

Любое лишнее поле => `ERROR` с `error_code=invalid_command_format`.

Внимание: `sig` проверяется только по формату (hex64), криптографическая проверка подписи отсутствует.

## 4.2. Дедупликация

- cache size: `32` (`COMMAND_DEDUP_CACHE_SIZE`)
- окно: `180` секунд (`COMMAND_DEDUP_WINDOW_SEC`)
- ключ дедупликации: только `cmd_id` (глобально на устройство, не per-node)

Повторный `cmd_id` silently игнорируется (без нового `command_response`).

## 4.3. Статусная модель ответа

Pipeline:

1. При валидной команде сразу отправляется `ACK`.
2. После выполнения отправляется terminal status:
   - `DONE`
   - `NO_EFFECT`
   - `BUSY`
   - `INVALID`
   - `ERROR`

Очередь команд (`COMMAND_QUEUE_LENGTH=32`) переполнена -> terminal `BUSY` (`command_queue_full`).

Приоритет обработки `state`:

- `state` обслуживается выделенной deferred queue (`STATE_COMMAND_QUEUE_LENGTH` + отдельный worker),
  чтобы критические проверки 2-бакового workflow получали causally-correct `IRR_STATE_SNAPSHOT`.
- Перед выполнением `state` worker ждёт quiet-window `1500 ms` после получения самого `state`
  и после последней non-state команды, а также пустую основную command queue и отсутствие
  in-flight команды у основного worker.
- При недоступности или переполнении выделенной state queue используется fail-safe fallback:
  постановка `state` в начало общей очереди (`xQueueSendToFront`).

## 4.4. Поддерживаемые команды

Команды, распознаваемые `resolve_command_kind`:

- `test_sensor`, `probe_sensor`
- `state`
- `report_config`, `config_report`, `get_config`, `sync_config`
- `restart`, `reboot`
- `set_relay`, `set_pwm`, `run_pump`, `dose`
- `emit_event`
- `set_fault_mode`
- `reset_state`
- `reset_binding`
- `activate_sensor_mode`, `deactivate_sensor_mode`

Особенность: неизвестный `cmd` попадает в `COMMAND_KIND_GENERIC` и обычно завершается `DONE` (`virtual_noop`), а не `INVALID`.
Исключение: `calibrate` на `ph_sensor`/`ec_sensor` завершается terminal `INVALID` с
`details.error=unsupported_sensor_calibration_command`, чтобы negative-path sensor calibration
не маскировался под успешный `virtual_noop`.

Параметры `storage_state/set_fault_mode`:

- `level_clean_min_override`, `level_clean_max_override`
- `level_solution_min_override`, `level_solution_max_override`
- `ph_value` -> принудительное текущее значение `ph_sensor` в диапазоне `4.8..7.2`
- `ec_value` -> принудительное текущее значение `ec_sensor` в диапазоне `0.4..3.2`

При изменении `*_override`, `ph_value` или `ec_value` test-node публикует immediate telemetry snapshot, чтобы real-hardware E2E не зависели от следующего periodic telemetry tick.

---

## 5. Режимы и state-поведение

## 5.1. Boot/Setup/Run

Если нет валидного Wi-Fi/MQTT конфига, запускается setup-портал:

- SSID: `TESTNODE_SETUP_<PIN>`
- URL: `http://192.168.4.1`
- пароль AP: `hydro2025`

После сохранения конфигурации происходит перезапуск и штатный boot.

## 5.2. Namespace режимы

Режимы:

- `configured`: рабочий namespace из NVS
- `preconfig`: `gh-temp/zn-temp`

Правило boot:

- если `gh_uid`/`zone_uid` отсутствуют или равны temp -> runtime стартует в `gh-temp/zn-temp`.

Обработка `.../config`:

- в `configured` режиме config из чужого namespace игнорируется;
- config из temp namespace принимается;
- namespace может меняться динамически (runtime) по payload `gh_uid/zone_uid`.

## 5.3. Sensor-mode (pH/EC)

По умолчанию:

- `ph_sensor_mode_active=false`
- `ec_sensor_mode_active=false`

Следствия:

- telemetry `ph_sensor/ec_sensor` не публикуется;
- команды на `pump_acid/pump_base/pump_a..pump_d` возвращают `ERROR` (`node_not_activated`).

Команды:

- `activate_sensor_mode`
- `deactivate_sensor_mode`

целевой способ отправки — через service-channel (`system`/`storage_state`) соответствующих нод.
В текущем runtime test-node эти команды распознаются по `cmd` и `node_uid` и не имеют
жёсткой привязки к конкретному channel.

### 5.3.1. Строгая модель EC/pH коррекций (фактическая)

Стартовые значения после `reset_state`:

- `pH = 6.90` (границы clamp: `4.8..7.2`)
- `EC = 0.60` (границы clamp: `0.4..3.2`)

Пассивный drift на тик телеметрии:

- `pH`: `drift + 0.0005`
- `EC`: `drift*2 - 0.0025`

где `drift` — детерминированная псевдо-динамика из telemetry loop.

Реакция коррекции:

- `pump_acid`: `pH -= 0.10 * scale * phase_factor`
- `pump_base`: `pH += 0.10 * scale * phase_factor`
- `pump_a..pump_d`: `EC += 0.055 * scale * phase_factor`

Phase factor:

- `solution_fill` path:
  - `pH`: `0.50`
  - `EC`: `0.50`
- `tank_recirc` path:
  - `pH`: `2.50`
  - `EC`: `3.20`
- вне fill/recirc path: `1.0`

Scale:

- при `params.ml > 0`: `scale = ml / nominal_ml`;
- иначе при `params.duration_ms > 0`: `scale = (duration_ms/1000) / nominal_ml`;
- далее `scale` ограничивается диапазоном `0.5..5.0`;
- nominal: `pH=8 ml`, `EC=12 ml`.

Наблюдаемость для backend/e2e:

- в `command_response.details` возвращаются `delta_ph/ph_after` или `delta_ec/ec_after`;
- telemetry `ph_sensor/ec_sensor` при active mode содержит:
  `flow_active`, `stable`, `corrections_allowed` (все синхронны состоянию sensor mode).

Fail-closed правило:

- любые команды дозирования/коррекции на pH/EC-каналах при неактивном sensor mode
  должны завершаться `ERROR` + `error_code=node_not_activated` (без изменения значения сенсора).

Transient-overlap правило для `pump_main`:

- `run_pump/dose` на `pump_main` не должен возвращать `BUSY`, если `pump_main` уже `ON` через `set_relay`;
- после завершения transient-команды исходное состояние `pump_main` восстанавливается
  (не допускается ложное выключение уже активного контура).

## 5.4. Режим reboot/reset

- `restart`/`reboot`:
  - публикуется `RESTARTING` для всех 5 нод;
  - terminal `command_response` (`DONE`);
  - аппаратный `esp_restart()`.
- `reset_state`:
  - сброс внутреннего симуляционного состояния.
- `reset_binding`:
  - пишет в NVS temp namespace (`gh-temp/zn-temp`);
  - runtime namespace меняется после reboot.

### 5.4.1. Каноничные AE3 real-hardware сценарии

- `E101_ae3_two_tank_realhw_setup_ready` — каноничный сценарий, который доводит two-tank систему до `workflow_phase=ready`; после этого полив разрешён.
- `E101_ae3_two_tank_realhw_ready_during_fill` — альтернативный happy-path, где `ready` достигается ещё на fill-path без recirculation.
- `E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw` — recovery-вариант: после first-run retry-limit второй прогон снова доводит систему до `ready`.
- `E104_ae3_two_tank_realhw_hot_reload_correction_config` — не тест “полив уже разрешён”, а strict hot-reload тест активного correction loop; он проверяет сходимость pH/EC и применение новой config version внутри `tank_recirc`.

---

## 6. Модель исполнения и симуляции

## 6.1. Задержки

- telemetry tick: `5000 ms`
- periodic `config_report`: `30000 ms`
- command base delay:
  - probe/state: `180..480 ms`
  - config-report cmd: `120..320 ms`
  - restart: `1200..2200 ms`
  - non-transient actuator control path (`set_relay`, `set_pwm`, `activate_sensor_mode`,
    `deactivate_sensor_mode`, `reset_state`, `set_fault_mode`): `120..260 ms`
  - transient (`run_pump`/`dose`): масштабируемая задержка, с ограничениями

Параметры управления:

- `params.sim_delay_ms`
- `params.sim_status`
- `params.sim_no_effect`

## 6.2. 2-бака (staged level model)

`clean_fill`:

- `level_clean_min=1` через 10s от старта stage
- `level_clean_max=1` через 30s (latch)

`solution_fill`:

- `level_solution_min=1` через 10s
- `level_solution_max=1` через 60s (latch)

События:

- `clean_fill_completed`
- `solution_fill_completed`
- при fault-mode:
  - `clean_fill_timeout`
  - `solution_fill_timeout`

Публикация: `hydro/{gh}/{zone}/nd-test-irrig-1/storage_state/event`.

## 6.3. Interlock для `pump_main`

`pump_main` включается только если одновременно:

- открыт хотя бы один `supply` клапан (`valve_clean_supply` или `valve_solution_supply`)
- открыт хотя бы один target-клапан (`valve_solution_fill` или `valve_irrigation`)

Иначе `ERROR` (`pump_interlock_blocked`).

---

## 7. Ограничения (критично для production-ready)

## 7.1. Ограничения транспорта

- MQTT RX payload limit: `2048` байт (буфер сборки в `mqtt_manager`).
- Сообщения длиннее отбрасываются до входа в callback.

## 7.2. Ограничения персистентности

- Полный `NodeConfig` из runtime MQTT intentionally не сохраняется в NVS.
- Persist namespace fallback разрешен только для `nd-test-irrig-1`.
- Для остальных виртуальных нод namespace runtime-only.

## 7.3. Ограничения security

- Нет криптографической проверки `sig`.
- Команда валидируется только по форме payload.
- `cmd_id` дедупликация глобальная (возможны коллизии между виртуальными нодами).

## 7.4. Ограничения контракта каналов

- Команды принимаются на alias/service каналах, не перечисленных в `config_report`.
- Это может создавать расхождение между backend-моделью каналов и runtime-фактом.

## 7.5. Ограничения командной семантики

- Большинство неизвестных `cmd` по-прежнему завершаются `DONE` (`virtual_noop`) вместо `INVALID`.
- Исключение сделано только для `calibrate` на `ph_sensor`/`ec_sensor`, где требуется terminal `INVALID`
  для negative-path sensor calibration.
- Остальные `virtual_noop` всё ещё могут маскировать ошибки оркестрации и не подходят для боевых нод.

## 7.6. Ограничения multi-node эмуляции

- LWT/topic identity и MQTT session физически едины для одного ESP.
- Это корректно для HIL эмуляции, но не эквивалентно 5 независимым устройствам.

---

## 8. Что обязательно для доведения реальных нод в боевой режим

## 8.1. Must-have изменения в real-node прошивках

1. Реальная проверка подписи команды (`sig`), а не только формат.
2. Строгий `INVALID` для неизвестных `cmd` и неподдерживаемых `channel/cmd`.
3. Дедупликация минимум в scope `{node_uid, channel, cmd_id}`.
4. Убрать runtime-only скрытые alias-каналы или явно документировать их в `config_report`.
5. Персистентность namespace/config должна быть per-device без shared key эффектов.
6. Полный NodeConfig должен проходить через MQTT размерно безопасно (увеличение лимитов или chunking policy).
7. Не принимать temp namespace config в configured режиме без явного policy/флага.
8. Удержать fail-closed поведение для EC/pH коррекций при неактивном sensor mode.

## 8.2. Acceptance-критерии перед production rollout

1. Узел корректно отрабатывает `ACK -> terminal` на всех поддерживаемых командах.
2. Нет `DONE` для неизвестных команд.
3. Каналы в `config_report` полностью совпадают с тем, что реально принимает командный runtime.
4. `activate_sensor_mode/deactivate_sensor_mode` детерминированно включают/выключают telemetry и коррекции.
5. Поток `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> Node` стабилен под retry/reconnect.
6. При reboot нет потери финального `command_response`.
7. Нет скрытых alias, ломающих модель backend.

## 8.3. AE3-Lite smoke на реальном test_node

Для native `ae3lite` two-tank smoke используется сценарий:

- `tests/e2e/scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml`

Сценарий проверяет:

1. `reset_state` проходит через `history-logger -> MQTT -> test_node`.
2. Зона временно переводится в `zones.automation_runtime='ae3'`.
3. `POST /zones/{id}/start-cycle` создаёт canonical `ae_task`.
4. Runtime публикует `storage_state/state` и `clean_fill_start` через `ae_commands/commands`.
5. Task доходит до `pending` со stage `clean_fill_check`, не падая в fail-closed.
6. `GET /internal/tasks/{task_id}` отражает тот же canonical pending status.

Запуск:

```bash
SCENARIO_SET=ae3lite tests/e2e/run_automation_engine_real_hardware.sh
```

Runtime wrapper поведения:

1. `tests/e2e/run_automation_engine_real_hardware.sh` auto-discover'ит live UID по heartbeat-топикам,
   используя `E2E_NODE_UID_REGEX` (default: `^nd-`).
2. Явные `TEST_NODE_UID`, `TEST_WORKFLOW_NODE_UID`, `TEST_PH_NODE_UID`, `TEST_EC_NODE_UID`
   остаются override-механизмом; default режим для них — `auto`.
3. После `config -> gh-temp/zn-temp` wrapper сначала ждёт temp heartbeat namespace.
4. Если temp heartbeat не появился вовремя, wrapper делает fallback и шлёт device-restart
   в исходный live namespace.
5. Reboot-path считается валидным только если узел возвращает terminal `command_response`
   со статусом `DONE`; при `INVALID|ERROR|BUSY|NO_EFFECT` wrapper останавливается fail-fast.

Предусловия:

1. В зоне `${TEST_NODE_ZONE_UID}` есть online real-hardware ноды, чьи heartbeat UID попадают под `E2E_NODE_UID_REGEX`,
   либо нужные UID явно заданы через `TEST_*`.
2. Primary/workflow нода поддерживает `system/${REAL_HW_REBOOT_CMD}` и возвращает terminal `DONE`
   через `command_response`; иначе hardware reset/bind stage считается несовместимым со smoke-harness.
3. `history-logger`, `automation-engine` и MQTT bridge доступны.
4. `telemetry_last` по `level_clean_*` и `level_solution_*` приходит от test-node и свежее runtime window.
5. Scheduler security baseline разрешает `POST /zones/{id}/start-cycle` и `GET /internal/tasks/{task_id}`.

---

## 9. Быстрый профиль test_node для e2e/hil

- Командная очередь: `32`
- Heartbeat/telemetry tick: `5s`
- Config-report periodic: `30s`
- Публикация node_hello: `hydro/node_hello`
- Virtual nodes: `5`
- Default base namespace: `gh-test-1/zn-test-1`
- Temp namespace: `gh-temp/zn-temp`

---

## 10. Связанные документы

- `firmware/test_node/README.md`
- `doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md`
- `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`
