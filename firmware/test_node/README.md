# Тестовая прошивка для E2E и HIL тестов

ESP32-прошивка, которая эмулирует несколько отдельных узлов Hydro 2.0 на одном устройстве.

## Назначение

Эта прошивка предназначена для:
- Проверки MQTT-контрактов на реальном ESP32 (HIL)
- Эмуляции полного набора узлов для шага "Устройства"
- Тестирования setup/preconfig режима
- E2E совместимости с backend/python

## Source of truth для production-доработок

Для доведения реальных нод до боевого режима используйте спецификацию:

- [`doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md`](../../doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md)
- [`doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md`](../../doc_ai/02_HARDWARE_FIRMWARE/TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md)

Документ фиксирует фактический контракт `test_node`: каналы, MQTT-топики, режимы, ограничения и обязательные критерии перед rollout.

## Функциональность

Прошивка эмулирует 6 виртуальных нод (разные `node_uid`):
- `nd-test-irrig-1` — объединённый узел полив + накопление
- `nd-test-ph-1` — коррекция pH
- `nd-test-ec-1` — коррекция EC
- `nd-test-soil-1` — датчик влажности субстрата
- `nd-test-climate-1` — климат (опционально)
- `nd-test-light-1` — свет (опционально)

Каналы объединённого узла `nd-test-irrig-1`:
- актуаторы: `pump_main`, `valve_clean_fill`, `valve_clean_supply`, `valve_solution_fill`, `valve_solution_supply`, `valve_irrigation`
- уровни баков: `level_clean_min`, `level_clean_max`, `level_solution_min`, `level_solution_max`

Каналы `nd-test-ph-1`:
- сенсор: `ph_sensor`
- актуаторы: `pump_acid`, `pump_base`, `system`

Каналы `nd-test-ec-1`:
- сенсор: `ec_sensor`
- актуаторы: `pump_a`, `pump_b`, `pump_c`, `pump_d`, `system`

Каналы `nd-test-soil-1`:
- сенсор: `soil_moisture`
- сервисный актуатор: `system`

Для каждой виртуальной ноды:
- публикуется `status`, `heartbeat`, `telemetry`, `config_report`
- принимаются команды в `.../{node_uid}/{channel}/command`
- отправляются `command_response` (`ACK` сразу + финальный статус после виртуального выполнения)

### Выполнение команд

- Поддержан режим эмуляции реального цикла `ACK -> DONE/INVALID/BUSY/ERROR`.
- Для actuator-команд добавлены реалистичные профили задержек:
  - `set_relay`, `set_pwm`, `activate_sensor_mode`, `deactivate_sensor_mode`, `reset_state` —
    короткие control-latency задержки `120..260 ms`;
  - `run_pump`, `dose` — длительность выполнения зависит от `duration_ms`/`ml` (масштабированно, чтобы тесты не были слишком длинными).
- Для idempotent-сценариев возвращается `NO_EFFECT` (например, повторный `set_relay` в уже установленное состояние).
  Для каналов водного контура (`main_pump`/клапаны/fill-drain) повторные команды и forced `sim_no_effect`
  нормализуются в `DONE`, чтобы не ломать пошаговые E2E сценарии наполнения баков.
- Для transient-актуаторов (`run_pump`, `dose`) добавлена проверка занятости канала с ответом `BUSY`.
  Исключение: `run_pump/dose` на `pump_main` допускается в overlap-режиме, если `pump_main`
  уже включен через `set_relay` (без ложного `BUSY` и без сброса состояния насоса в `OFF` после transient).
- Команда `calibrate` на `ph_sensor`/`ec_sensor` не поддерживается и завершается terminal `INVALID`
  с `details.error=unsupported_sensor_calibration_command`, чтобы real-hardware negative-path для
  sensor calibration проходил через тот же protected command pipeline, что и боевой backend.
- Команда `state` обрабатывается через отдельную deferred queue (`storage_state/state` barrier path).
  Worker для `state` ждёт quiet-window `1500 ms` после прихода самого `state` и после последней non-state команды,
  а также пустую основную command queue и отсутствие in-flight команды в основном worker.
  Это нужно, чтобы `IRR_STATE_SNAPSHOT` не снимался раньше actuator-команд из других MQTT topic.
  Если выделенная state queue недоступна или переполнена, используется fallback:
  постановка `state` в начало общей очереди (`queue front`).
- Для 2-бакового контура добавлена staged-модель датчиков уровня:
  - стартовое состояние: `level_clean_min/max=0`, `level_solution_min/max=0`;
  - при `clean_fill`:
    - `level_clean_min=1` **сразу** при открытом пути наполнения (`valve_clean_fill` / `tank_fill`) или при
      активном `solution_fill` (подача из чистого контура), чтобы AE3 с `clean_fill_min_check_delay_ms=0`
      не получал ложный `clean_fill_source_empty` до роста `water_level` над порогом;
    - `level_clean_max=1` через 30 секунд и фиксируется;
  - при `solution_fill`:
    - `level_solution_min=1` **сразу** при активном пути (насос + `valve_clean_supply` + `valve_solution_fill`);
    - `level_solution_max=1` через 180 секунд и фиксируется.
  - для каждого подтверждённого изменения `level_clean_min`, `level_clean_max`,
    `level_solution_min`, `level_solution_max` публикуется отдельный channel-event
    `hydro/{gh}/{zone}/nd-test-irrig-1/{level_channel}/event` с
    `event_code=level_switch_changed`, `channel`, `state`, `initial`, `snapshot`;
  - после boot/MQTT reconnect виртуальная IRR-нода один раз перепубликует initial-state
    события по всем четырём `level_*` каналам;
  - guard-события `clean_fill_source_empty`, `solution_fill_source_empty`,
    `solution_fill_leak_detected`, `recirculation_solution_low`, `irrigation_solution_low`,
    `clean_fill_completed`, `solution_fill_completed`, `emergency_stop_activated`
    публикуются в `hydro/{gh}/{zone}/nd-test-irrig-1/storage_state/event`
    c `event_code`, `ts`, `snapshot`, `state`.
- Для контуров pH/EC добавлен управляемый тестовый профиль:
  - старт после `reset_state`: `pH=6.9`, `EC=0.6` (формируются отклонения для коррекций);
  - пассивный drift смещён так, чтобы отклонения возникали стабильно, но при активной коррекции
    контур сходился к target в рамках startup/recirculation окна;
  - фактический drift на telemetry tick:
    - `pH += drift + 0.0002`
    - `EC += drift*2 - 0.0010`
  - реакция correction больше не мгновенная:
    - после дозы эффект появляется с задержкой `~4 сек` (`2` telemetry tick при периоде `2 сек`);
    - первый observed sample даёт пик реакции;
    - затем transient-часть эффекта затухает ещё `~8 сек`, после чего остаётся residual-смещение;
    - если stacked correction упирается в clamp сенсора, transient decay рассчитывается только по реально
      достигнутому приращению, чтобы test-node не проваливался ниже seeded baseline из-за самого симулятора;
    - это имитирует in-flow correction в смесителе, где значение меняется волной, а затем постепенно падает;
    - чтобы реальный `ae3` observe-window не терял residual раньше времени, пассивный drift-bias
      дополнительно подавляется после correction:
      - `~120 сек` для flow-path (`solution_fill` / `tank_recirc` / `irrigation`);
      - `~24 сек` вне flow-path;
  - базовая амплитуда correction:
    - `pump_acid/pump_base`: `delta_pH = 0.12 * scale * phase_factor`
    - `pump_a..pump_d`: `delta_EC = 0.068 * scale * phase_factor`
  - phase factor:
    - `solution_fill` (проточная коррекция): `pH=2.20`, `EC=2.90`
    - `tank_recirc` (проточная коррекция): `pH=2.50`, `EC=3.20`
    - `irrigation` (проточная коррекция): `pH=2.85`, `EC=3.75`
    - вне этих путей: `1.0`
  - по умолчанию `nd-test-ph-1` и `nd-test-ec-1` в `deactivate`:
    - не публикуют `ph_sensor/ec_sensor` telemetry;
    - команды коррекции (`pump_acid/pump_base/pump_a..pump_d`) отклоняются c `ERROR` + `error_code=node_not_activated`;
  - после `system/activate_sensor_mode` соответствующая нода начинает публиковать telemetry и принимать коррекции;
    - при активации сразу публикуется свежий snapshot;
    - затем штатная telemetry идёт каждые `2 сек`;
  - correction-каналы `pump_acid/pump_base/pump_a..pump_d` принимают только `cmd="dose"` с `params.ml > 0`;
  - `run_pump` для correction-каналов отклоняется как `INVALID` с `error_code=unsupported_correction_command`;
  - реакция на сенсоры для correction-каналов масштабируется только по `params.ml`,
    nominal `pH=8 ml`, `EC=12 ml`, clamp `scale=0.5..5.0`,
    и отражается в `command_response.details` (`ph_after/ec_after`, `delta_*`, `effect_delay_sec`, `effect_decay_sec`).
- Для `nd-test-soil-1` добавлена реактивная модель влажности субстрата:
  - стартовое значение после `reset_state`: `soil_moisture=43%`;
  - при открытии `valve_irrigation` или активном irrigation path (`pump_irrigation` либо `pump_main + valve_solution_supply + valve_irrigation`) влажность растёт на каждом telemetry tick;
  - без полива влажность уходит вниз через dry-back, зависящий от температуры воздуха;
  - telemetry публикуется в канале `soil_moisture` с метрикой `SOIL_MOISTURE`.
- Входящий `command` валидируется строго по canonical-полям:
  `{cmd_id, cmd, params, ts, sig}` (без дополнительных полей).
- Для `sig` требуется hex-строка длиной 64 символа.
- `config_report` публикуется:
  - при подключении к MQTT;
  - по командам `report_config`, `config_report`, `get_config`, `sync_config`.
- Для `nd-test-irrig-1` в `config_report` и в ответе `storage_state/state`
  добавляется top-level объект `fail_safe_guards`:
  - `clean_fill_min_check_delay_ms`
  - `solution_fill_clean_min_check_delay_ms`
  - `solution_fill_solution_min_check_delay_ms`
  - `recirculation_solution_min_guard_enabled`
  - `irrigation_solution_min_guard_enabled`
  - `estop_debounce_ms`
- Добавлена сервисная команда `system/reset_state`:
  - сбрасывает runtime-состояние симулятора в стартовые значения;
  - возвращает уровни баков в `0` (`level_*_min/max=0`), очищает latch-флаги 2-бакового контура;
  - сбрасывает ручные `*_override` для level-switch датчиков обратно в `auto`;
  - выключает виртуальные актуаторы и очищает in-flight staged fill-таймеры.
- Для совместимости e2e-сценариев добавлены alias-каналы:
  - на `nd-test-climate-1`: `fan`, `heater` (дополнительно к `fan_air`).
  - `nd-test-irrig-1` публикует только профиль IRR:
    `pump_main`, `valve_*`, `level_*`.
- Добавлена сервисная команда `system/reset_binding`:
  - сохраняет в NVS preconfig namespace `gh-temp/zn-temp` (привязка к зоне сбрасывается);
  - runtime namespace меняется после `system/reboot`/`system/restart`.
- При получении `.../{node}/config` тест-нода сохраняет в NVS только базовый config/namespace
  для `nd-test-irrig-1` (общий key), чтобы не перетирать namespace всех виртуальных нод.
  Для остальных виртуальных нод namespace обновляется только в runtime и сразу публикуется `config_report`.
- Команда `system/reboot` (`restart`) в test-node выполняет **аппаратный reboot ESP32**:
  - перед reboot публикуется `command_response` со статусом `DONE`;
  - дополнительно публикуется `RESTARTING` для всех виртуальных нод;
  - после старта нода поднимается заново по обычному boot flow (MQTT reconnect, heartbeat, node_hello/config_report).
- Интервал heartbeat и telemetry: `2` секунды.

#### Параметры симуляции в `params` (опционально)

- `sim_delay_ms` — принудительная задержка финального ответа (мс).
- `sim_status` — принудительный terminal статус (`DONE|NO_EFFECT|BUSY|INVALID|ERROR`).
- `sim_no_effect` — быстрый способ принудить `NO_EFFECT=true`.

Для команды `system/set_fault_mode` на канале `storage_state`:
- `level_clean_min_override` — принудительное состояние датчика `level_clean_min` (`true|false`).
- `level_clean_max_override` — принудительное состояние датчика `level_clean_max` (`true|false`).
- `level_solution_min_override` — принудительное состояние датчика `level_solution_min` (`true|false`).
- `level_solution_max_override` — принудительное состояние датчика `level_solution_max` (`true|false`).
- `estop_pressed` — виртуально нажать/отпустить `E-Stop` для `nd-test-irrig-1` (`true|false`);
  при `true` test-node останавливает все IRR-актуаторы и публикует `emergency_stop_activated`,
  при `false` восстанавливает прерванный до stop runtime-path.
- `ph_value` — принудительно установить текущее значение `ph_sensor` в диапазоне `4.0..8.0`.
- `ec_value` — принудительно установить текущее значение `ec_sensor` в диапазоне `0.4..3.2`.
- `soil_moisture_pct` — принудительно установить текущую влажность субстрата в диапазоне `0..100`.
- Для возврата в автоматический режим используйте значение `< 0` (например, `-1`) у нужного `*_override`.
- При изменении `*_override`, `ph_value`, `ec_value` или `soil_moisture_pct` тест-нода сразу публикует свежий telemetry snapshot, без ожидания следующего `2s` tick.

Каноничное real-hardware использование:

- `E101/E102/E103/E104/E105` обычно стартуют из дефолтного `reset_state` профиля (`pH=6.9`, `EC=0.6`).
- `E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle` дополнительно seed-ит recirculation раствор через
  `storage_state/set_fault_mode` в `ph_value=5.68`, `ec_value=1.92` перед strict sequential correction check.
- Это нужно не для послабления target, а чтобы сценарий после полного рестарта стенда
  стабильно проверял порядок `EC -> observe -> PH`, наблюдаемый delayed/decaying response и финальное попадание в strict target window,
  а не выносливость correction loop от cold-start точки `6.9/0.6`.

## Локальный UI (ESP32-S3)

В `test_node` добавлена поддержка локального UI:
- дисплей `ILI9341` (SPI, через `esp_lcd` + `LVGL`);
- энкодер (тип input `LV_INDEV_TYPE_ENCODER`).
- экран инициализируется первым в `app_main`, затем на нем показываются шаги инициализации
  (сетевой стек, config storage, setup-портал, Wi‑Fi, MQTT, запуск worker-задач).

Пины по умолчанию:
- ILI9341: `SCLK=12`, `MOSI=11`, `MISO=-1`, `DC=9`, `RST=14`, `CS=10`, `BL=15`
- Encoder: `A/CLK=5`, `B/DT=4`, `SW=6`

Дефолты экрана (как в официальном `spi_lcd_touch`):
- `LCD SPI pixel clock = 20 MHz`
- `LVGL draw buffer lines = 20`
- `LCD SPI queue depth = 10`
- `LVGL single draw buffer = OFF` (двойной буфер)
- `LVGL RGB565 byte swap = ON`
- `LCD mirror = X:ON, Y:OFF`

Параметры можно менять через `menuconfig` в секции `Test Node UI`.

## Компиляция

```bash
cd firmware/test_node
source /home/georgiy/esp/esp-idf/export.sh
idf.py build
```

## Использование

1. Загрузите прошивку на устройство
2. Настройте WiFi и MQTT в конфигурации
3. Запустите тест совместимости:

```bash
# Используйте скрипт запуска тестов
./firmware/tests/run_compatibility_tests.sh

# Или напрямую
python3 firmware/tests/test_node_compatibility.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-test-001
```

## Форматы сообщений

Все сообщения соответствуют контракту MQTT 2.0:
- Телеметрия: `{metric_type, value, ts}`
- Команда в узел: `{cmd_id, cmd, params, ts, sig}`
- Ответы на команды: `{cmd_id, status, details?, ts}`
- Heartbeat: `{uptime, free_heap, rssi?}`
- Статус: `{status, ts}`

## Setup/preconfig режим

Если в NVS нет валидных WiFi/MQTT настроек, прошивка автоматически запускает setup-портал:
- AP SSID: `TESTNODE_SETUP_<PIN>`
- веб-форма: `http://192.168.4.1`
- после сохранения данных устройство перезапускается

Если `gh_uid=gh-temp` или `zone_uid=zn-temp`, прошивка работает в preconfig namespace:
- публикует данные в temp namespace `hydro/gh-temp/zn-temp/...`
- принимает команды для виртуальных нод в том же namespace
- продолжает эмулировать отдельные ноды, а не один общий узел

Подробнее о тестах: [`../tests/README.md`](../tests/README.md)

---

**Версия:** 1.0
