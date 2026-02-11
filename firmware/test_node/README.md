# Тестовая прошивка для E2E и HIL тестов

ESP32-прошивка, которая эмулирует несколько отдельных узлов Hydro 2.0 на одном устройстве.

## Назначение

Эта прошивка предназначена для:
- Проверки MQTT-контрактов на реальном ESP32 (HIL)
- Эмуляции полного набора узлов для шага "Устройства"
- Тестирования setup/preconfig режима
- E2E совместимости с backend/python

## Функциональность

Прошивка эмулирует 6 виртуальных нод (разные `node_uid`):
- `nd-test-irrig-1` — полив
- `nd-test-ph-1` — коррекция pH
- `nd-test-ec-1` — коррекция EC
- `nd-test-tank-1` — накопительный узел
- `nd-test-climate-1` — климат (опционально)
- `nd-test-light-1` — свет (опционально)

Для каждой виртуальной ноды:
- публикуется `status`, `heartbeat`, `telemetry`, `config_report`
- принимаются команды в `.../{node_uid}/{channel}/command`
- отправляются `command_response` (`ACK` сразу + финальный статус после виртуального выполнения)

### Выполнение команд

- Поддержан режим эмуляции реального цикла `ACK -> DONE/INVALID/BUSY`.
- `config_report` публикуется:
  - при подключении к MQTT;
  - по командам `report_config`, `config_report`, `get_config`, `sync_config`.
- Интервал heartbeat и telemetry: `5` секунд.

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
