# I²C Bus Component

Общий драйвер I²C шины (ESP-IDF `i2c_master` v2) с thread-safe доступом для ESP32-нод Hydro 2.0.

## Контракт и инварианты (A)

- **Порядок блокировок:** сначала mutex **драйвера** сенсора/подсистемы, затем вызовы `i2c_bus_*`. Не вызывать код драйвера, который снова берёт I²C, **удерживая** mutex `i2c_bus` — риск deadlock.
- **Повторы:** автоматические повторы **только для чтения** и только в `i2c_bus_read_bus_ex` при `read_extra_retries > 0`. `i2c_bus_read_bus` / `read_byte` — **одна** попытка (обратная совместимость). **Запись** — всегда одна попытка (без автоповтора), чтобы не дублировать неидемпотентные команды.
- **Кэш `i2c_master_dev_handle_t`:** per (шина, 7-bit адрес). Сброс кэша: `i2c_bus_deinit`, `i2c_bus_recover`, успешный `i2c_bus_reset_bus`, `i2c_bus_forget_device` (обязателен при **смене 7-bit адреса** Trema и т.п.).
- **Таймауты:** `xfer_timeout_ms` — лимит одной транзакции IDF; `lock_timeout_ms == 0` в `i2c_bus_xfer_opts_t` означает авто: `max(xfer + 50 мс, 50 мс)` для ожидания mutex.
- **Запись без heap:** суммарная длина `reg_prefix + payload` ≤ `I2C_BUS_MAX_COMBINED_WRITE` (64); иначе `ESP_ERR_INVALID_ARG`.

## Инициализация

Ручная:

```c
i2c_bus_config_t config = {
    .sda_pin = 21,
    .scl_pin = 22,
    .clock_speed = 100000,
    .pullup_enable = false
};
ESP_ERROR_CHECK(i2c_bus_init_bus(I2C_BUS_0, &config));
```

Из NodeConfig (`i2c_bus_init_from_config`):

- `hardware.i2c` — шина **0** (как раньше).
- Опционально `hardware.i2c1` — шина **1** (те же поля: `sda`, `scl`, `speed`, опционально `pullup`). **По умолчанию** в прошивке и в `i2c_bus_init_from_config` внутренние pull-up **выключены** (`pullup: false`); включайте `pullup: true` в JSON только если нужны слабые внутренние подтяжки ESP.

**Частичная инициализация:** сначала всегда поднимается шина 0. Если задан `hardware.i2c1`, а `i2c_bus_init_bus(I2C_BUS_1, …)` завершился с ошибкой, **шина 0 остаётся инициализированной** (в лог пишется предупреждение). Вызывающий получает код ошибки шины 1 и может повторить инициализацию или поднять шину 1 вручную.

См. `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` (раздел `hardware`).

## Чтение / запись

Legacy (одна попытка чтения):

```c
uint8_t buf[2];
esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, 0x09, &reg, 1, buf, 2, 1000);
```

С опциями (повторы read + раздельные таймауты):

```c
i2c_bus_xfer_opts_t o = {
    .xfer_timeout_ms = 500,
    .lock_timeout_ms = 0,       /* авто */
    .read_extra_retries = 2,    /* до 3 попыток всего */
};
err = i2c_bus_read_bus_ex(I2C_BUS_1, 0x09, &reg, 1, buf, 2, &o);
```

После смены адреса устройства на шине:

```c
/* ESP_OK — слот удалён; ESP_ERR_NOT_FOUND — адреса не было в кэше (часто безвредно) */
(void)i2c_bus_forget_device(I2C_BUS_1, old_addr_7bit);
```

## Сканирование / recover

- `i2c_bus_scan_bus` — временные dev-handle, кэш шины не засоряется.
- `i2c_bus_recover` — полный deinit+init шины **0** (как в API ранее).
- `i2c_bus_reset_bus` — FSM reset; при успехе кэш dev на этой шине очищается.

## Зависимости

ESP-IDF 5.x, FreeRTOS, `config_storage` + cJSON для `init_from_config`.

## Документация

- `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` (`hardware.i2c` / `i2c1`)
- Компонент `i2c_cache`: политика кэширования чтений — `../i2c_cache/README.md`
