# TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md
# Спецификация test_node для доведения реальных нод до боевого режима

**Версия:** 1.0  
**Дата обновления:** 2026-03-02  
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

Особенность: неизвестный `cmd` попадает в `COMMAND_KIND_GENERIC` и завершается `DONE` (`virtual_noop`), а не `INVALID`.

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

- `pH`: `drift + 0.004`
- `EC`: `drift*4 - 0.006`

где `drift` — детерминированная псевдо-динамика из telemetry loop.

Реакция коррекции:

- `pump_acid`: `pH -= 0.03 * scale`
- `pump_base`: `pH += 0.03 * scale`
- `pump_a..pump_d`: `EC += 0.05 * scale`

Scale:

- при `params.ml > 0`: `scale = ml / nominal_ml`;
- иначе при `params.duration_ms > 0`: `scale = (duration_ms/1000) / nominal_ml`;
- далее `scale` ограничивается диапазоном `0.5..4.0`;
- nominal: `pH=8 ml`, `EC=12 ml`.

Наблюдаемость для backend/e2e:

- в `command_response.details` возвращаются `delta_ph/ph_after` или `delta_ec/ec_after`;
- telemetry `ph_sensor/ec_sensor` при active mode содержит:
  `flow_active`, `stable`, `corrections_allowed` (все синхронны состоянию sensor mode).

Fail-closed правило:

- любые команды дозирования/коррекции на pH/EC-каналах при неактивном sensor mode
  должны завершаться `ERROR` + `error_code=node_not_activated` (без изменения значения сенсора).

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

---

## 6. Модель исполнения и симуляции

## 6.1. Задержки

- telemetry tick: `5000 ms`
- periodic `config_report`: `30000 ms`
- command base delay:
  - probe/state: `180..480 ms`
  - config-report cmd: `120..320 ms`
  - restart: `1200..2200 ms`
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

- Неизвестные `cmd` завершаются `DONE` (`virtual_noop`) вместо `INVALID`.
- Это маскирует ошибки оркестрации и не подходит для боевых нод.

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
