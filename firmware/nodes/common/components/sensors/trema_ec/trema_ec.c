/**
 * @file trema_ec.c
 * @brief Драйвер Trema EC (iarduino_I2C_TDS) — I²C на шине ec_node (см. `TREMA_EC_I2C_BUS`)
 *
 * Поведение транспорта согласовано с **iarduino_I2C_TDS 1.3.3** (`_readBytes` / `_writeBytes`):
 * до 10 повторов при сбое, **1 ms** между попытками (`vTaskDelay`), **500 µs** после успешного чтения
 * (`esp_rom_delay_us`), **10 ms** после успешной записи (`vTaskDelay`) — см. upstream `iarduino_I2C_TDS.cpp`.
 *
 * Публичный API покрывает методы **iarduino_I2C_TDS** 1.3.3 (см. `reference/README.md`).
 * Шина 0 — OLED/INA209; см. `ec_node_defaults.h` и README ec_node.
 *
 * Потокобезопасность:
 * - Один **mutex** (не рекурсивный) на весь драйвер: I²C и поля состояния только под ним.
 *   Рекурсивный mutex **не** используем: `trema_ec_read` вызывает `trema_ec_init_locked()` уже
 *   под тем же lock — отдельный рекурсивный take не нужен (нет риска «зацикливания», только был
 *   бы риск **взаимной блокировки** при `read`→`init` с обычным mutex).
 * - В ESP-IDF `xSemaphoreCreateMutexStatic` даёт mutex с **наследованием приоритета** (как у динамического mutex).
 * - Mutex: **статический** (`xSemaphoreCreateMutexStatic`) — не зависит от heap, нет гонки «mutex=NULL,
 *   но код без блокировки» при OOM.
 * - Порядок блокировок: сначала mutex `trema_ec`, затем внутри `i2c_bus_*` — mutex шины. Не вызывать
 *   `trema_ec_*`, удерживая mutex `i2c_bus` той же шины (возможен deadlock с другой задачей).
 * - Опционально: очередь глубины 1 — снимок после `trema_ec_push_telemetry_snapshot` (один poll за тик), MQTT/OLED через
 *   `trema_ec_try_cached_measurement` без второго I²C в том же тике (см. `ec_node_tasks`).
 */

#include "trema_ec.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/portmacro.h"
#include <math.h>
#include <stdlib.h>

static const char *TAG = "trema_ec";

/** ID линейки чипов Flash-I²C / Metro — как в `iarduino_I2C_TDS.h`. */
#define TREMA_EC_CHIP_ID_FLASH 0x3CU
#define TREMA_EC_CHIP_ID_METRO 0xC3U
#define TREMA_EC_FLG_RESET     0x80U
#define TREMA_EC_BIT_SET_RESET 0x80U

/** Шина Trema EC на ec_node — только I2C_BUS_1 (отдельная линия от OLED), как ph_node + Trema pH. */
#define TREMA_EC_I2C_BUS I2C_BUS_1

/** Рабочий 7-bit адрес: дефолт из `TREMA_EC_ADDR`, после init может быть найден перебором. */
static uint8_t s_ec_i2c_addr = TREMA_EC_ADDR;

/** После полной неудачной попытки init не дёргать I²C до этого тика (избегает лавины при опросе телеметрии). */
static TickType_t s_init_backoff_until_tick;

/** Перебор адреса как в `iarduino_I2C_TDS::_begin`: `for (i=1; i<127; i++)`. */
#define TREMA_EC_ADDR_PROBE_FIRST 1
#define TREMA_EC_ADDR_PROBE_LAST  126

/** Как `iarduino_I2C_TDS::_readBytes` / `_writeBytes`: число повторов при NACK/таймауте. */
#define TREMA_EC_I2C_XFER_MAX_TRIES 10

/** Пауза между пакетами I²C после успешного чтения (upstream `delayMicroseconds(500)`). */
#define TREMA_EC_INTER_READ_GAP_US 500U

/** После успешной записи в регистры модуля (upstream `delay(10)`). */
#define TREMA_EC_POST_WRITE_DELAY_MS 10U

static StaticSemaphore_t s_ec_mutex_storage;
static SemaphoreHandle_t s_ec_mutex;
static portMUX_TYPE s_ec_mutex_create_spin = portMUX_INITIALIZER_UNLOCKED;

static void trema_ec_mutex_take(void)
{
    portENTER_CRITICAL(&s_ec_mutex_create_spin);
    if (s_ec_mutex == NULL) {
        s_ec_mutex = xSemaphoreCreateMutexStatic(&s_ec_mutex_storage);
        if (s_ec_mutex == NULL) {
            portEXIT_CRITICAL(&s_ec_mutex_create_spin);
            ESP_LOGE(TAG, "trema_ec: xSemaphoreCreateMutexStatic failed");
            abort();
        }
    }
    portEXIT_CRITICAL(&s_ec_mutex_create_spin);

    (void)xSemaphoreTake(s_ec_mutex, portMAX_DELAY);
}

static void trema_ec_mutex_give(void)
{
    (void)xSemaphoreGive(s_ec_mutex);
}

/** Очередь глубины 1: последний снимок после телеметрии (`trema_ec_push_telemetry_snapshot`). */
static QueueHandle_t s_sample_q;

void trema_ec_bind_sample_queue(QueueHandle_t queue)
{
    trema_ec_mutex_take();
    s_sample_q = queue;
    trema_ec_mutex_give();
}

void trema_ec_unbind_sample_queue(void)
{
    trema_ec_mutex_take();
    s_sample_q = NULL;
    trema_ec_mutex_give();
}

bool trema_ec_try_cached_measurement(trema_ec_measurement_t *out, uint32_t max_age_ms)
{
    if (out == NULL) {
        return false;
    }
    /* Сериализация с push/bind: как `trema_ph_try_cached_measurement`. */
    trema_ec_mutex_take();
    QueueHandle_t q = s_sample_q;
    if (q == NULL) {
        trema_ec_mutex_give();
        return false;
    }
    trema_ec_measurement_t tmp;
    if (xQueuePeek(q, &tmp, 0) != pdTRUE || !tmp.valid) {
        trema_ec_mutex_give();
        return false;
    }
    TickType_t age = xTaskGetTickCount() - tmp.tick_stamp;
    if (age > pdMS_TO_TICKS(max_age_ms)) {
        trema_ec_mutex_give();
        return false;
    }
    *out = tmp;
    trema_ec_mutex_give();
    return true;
}

void trema_ec_push_telemetry_snapshot(float ec_mScm, uint16_t raw_ec_u16, bool using_stub)
{
    if (s_sample_q == NULL) {
        return;
    }

    const bool valid = !using_stub && isfinite(ec_mScm) && !isnan(ec_mScm) && ec_mScm > 0.0f && ec_mScm <= 20.0f;

    trema_ec_mutex_take();
    trema_ec_measurement_t m = {
        .ec_mScm = ec_mScm,
        .raw_ec_u16 = raw_ec_u16,
        .using_stub = using_stub,
        .valid = valid,
        .tick_stamp = xTaskGetTickCount(),
    };
    (void)xQueueOverwrite(s_sample_q, &m);
    trema_ec_mutex_give();
}

static bool use_stub_values = false;
static float stub_ec = 1.2f;
static uint16_t stub_tds = 800;
static trema_ec_error_t last_error = TREMA_EC_ERROR_NONE;
static float last_temperature_c = NAN;
static uint8_t data[4];
static bool sensor_initialized = false;

/** Последнее слово с REG_TDS_EC после успешного I²C read (2 байта), для отладки всплесков. */
static uint16_t s_last_ec_reg_u16 = 0;
static bool s_last_ec_reg_u16_valid = false;

/** Как `valVers` в iarduino: байт REG_VERSION из блока 0x04… после валидации. */
static uint8_t s_module_fw_version;

bool trema_ec_is_initialized(void)
{
    bool v = false;
    trema_ec_mutex_take();
    v = sensor_initialized;
    trema_ec_mutex_give();
    return v;
}

static void trema_ec_i2c_after_read_pause(void)
{
    esp_rom_delay_us(TREMA_EC_INTER_READ_GAP_US);
}

/**
 * Чтение регистров: как `iarduino_I2C_TDS::_readBytes` — до 10 попыток, 1 ms между, 500 µs после успеха.
 * Вызывать при удержанном `s_ec_mutex`.
 */
static bool trema_ec_read_reg(uint8_t addr, uint8_t reg, uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    for (int attempt = 0; attempt < TREMA_EC_I2C_XFER_MAX_TRIES; attempt++) {
        esp_err_t err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, addr, &reg, 1, buf, len, timeout_ms);
        if (err == ESP_OK) {
            trema_ec_i2c_after_read_pause();
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    return false;
}

/**
 * Запись в регистры: как `iarduino_I2C_TDS::_writeBytes` — до 10 попыток, 1 ms между, 10 ms после успеха.
 */
static bool trema_ec_write_reg(uint8_t addr, uint8_t reg, const uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    for (int attempt = 0; attempt < TREMA_EC_I2C_XFER_MAX_TRIES; attempt++) {
        esp_err_t err = i2c_bus_write_bus(TREMA_EC_I2C_BUS, addr, &reg, 1, buf, len, timeout_ms);
        if (err == ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(TREMA_EC_POST_WRITE_DELAY_MS));
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    return false;
}

static bool trema_ec_read_model_at_addr(uint8_t addr, uint8_t *model_out, uint32_t timeout_ms)
{
    (void)timeout_ms;
    return trema_ec_read_reg(addr, REG_MODEL, model_out, 1, 500);
}

/** REG_ADDRESS (байт 3 блока с 0x04): как в iarduino — (addr>>1 from stored) или 0xFF/0x00 «не задано», или (addr<<1)|1 после changeAddress. */
static bool trema_ec_address_reg_matches(uint8_t addr_7bit, uint8_t reg_address_byte)
{
    if (reg_address_byte == 0xFF || reg_address_byte == 0x00) {
        return true;
    }
    if ((reg_address_byte >> 1) == addr_7bit) {
        return true;
    }
    if (reg_address_byte == (uint8_t)((addr_7bit << 1) | 1)) {
        return true;
    }
    return false;
}

/** Как `_begin` + проверка в `iarduino_I2C_TDS.cpp`: 4 байта с 0x04 — MODEL, VERSION, ADDRESS, CHIP_ID. */
static bool trema_ec_validate_id_block(uint8_t addr_7bit, const uint8_t d[4])
{
    if (d[0] != TREMA_EC_DEF_MODEL_TDS) {
        return false;
    }
    if (!trema_ec_address_reg_matches(addr_7bit, d[2])) {
        return false;
    }
    if (d[3] != TREMA_EC_CHIP_ID_FLASH && d[3] != TREMA_EC_CHIP_ID_METRO) {
        return false;
    }
    return true;
}

/**
 * Программный reset модуля — как `iarduino_I2C_TDS::reset()` после успешной идентификации в `_begin`.
 * После reset модуль может кратко отпускать подтяжки; на ESP остаёмся мастером на той же шине.
 */
static bool trema_ec_module_reset(void)
{
    uint8_t bits = 0;
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_BITS_0, &bits, 1, 200)) {
        return false;
    }
    bits |= TREMA_EC_BIT_SET_RESET;
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_BITS_0, &bits, 1, 200)) {
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
    /* Модуль на время reset отпускает подтяжки SDA/SCL — в iarduino сразу вызывают Wire.begin().
     * Эквивалент: сброс FSM мастера I²C без удаления шины (общая линия с OLED/INA). */
    (void)i2c_bus_reset_bus(TREMA_EC_I2C_BUS);
    for (int n = 0; n < 40; n++) {
        uint8_t flg = 0;
        if (!trema_ec_read_reg(s_ec_i2c_addr, REG_FLAGS_0, &flg, 1, 150)) {
            return false;
        }
        if (flg & TREMA_EC_FLG_RESET) {
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    return false;
}

/**
 * Полная инициализация датчика. Вызывать только при уже удержанном `trema_ec_mutex_take()`.
 */
static bool trema_ec_init_locked(void)
{
    bool ok = false;

    if (sensor_initialized) {
        return true;
    }

    if (s_init_backoff_until_tick != 0 && xTaskGetTickCount() < s_init_backoff_until_tick) {
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        ESP_LOGE(TAG, "I²C bus %d не инициализирован (Trema EC на ec_node — шина 1, см. ec_node_defaults.h)",
                 (int)TREMA_EC_I2C_BUS);
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    s_ec_i2c_addr = TREMA_EC_ADDR;
    uint8_t model = 0;
    uint8_t id4[4];
    bool found = false;

    if (trema_ec_read_model_at_addr(s_ec_i2c_addr, &model, 500) && model == TREMA_EC_DEF_MODEL_TDS) {
        /* Как iarduino после checkAddress: короткая пауза перед блоком чтения. */
        vTaskDelay(pdMS_TO_TICKS(2));
        if (trema_ec_read_reg(s_ec_i2c_addr, REG_MODEL, id4, sizeof(id4), 200) &&
            trema_ec_validate_id_block(s_ec_i2c_addr, id4)) {
            found = true;
        }
    }

    if (!found) {
        if (model == TREMA_EC_DEF_MODEL_TDS) {
            ESP_LOGW(TAG, "Trema EC: model 0x19 на 0x%02X, но блок ID (4 B с 0x04) не совпал — перебор 0x%02X–0x%02X",
                     s_ec_i2c_addr, TREMA_EC_ADDR_PROBE_FIRST, TREMA_EC_ADDR_PROBE_LAST);
        } else {
            ESP_LOGW(TAG, "Trema EC: нет валидного ответа на 0x%02X, перебор 0x%02X–0x%02X (bus %d)",
                     s_ec_i2c_addr, TREMA_EC_ADDR_PROBE_FIRST, TREMA_EC_ADDR_PROBE_LAST, (int)TREMA_EC_I2C_BUS);
        }

        for (int ai = TREMA_EC_ADDR_PROBE_FIRST; ai <= TREMA_EC_ADDR_PROBE_LAST; ai++) {
            uint8_t addr = (uint8_t)ai;
            if (!trema_ec_read_model_at_addr(addr, &model, 60)) {
                continue;
            }
            if (model != TREMA_EC_DEF_MODEL_TDS) {
                vTaskDelay(pdMS_TO_TICKS(1));
                continue;
            }
            if (!trema_ec_read_reg(addr, REG_MODEL, id4, sizeof(id4), 200) || !trema_ec_validate_id_block(addr, id4)) {
                vTaskDelay(pdMS_TO_TICKS(1));
                continue;
            }
            s_ec_i2c_addr = addr;
            ESP_LOGI(TAG, "Trema EC: найден по полному ID-блоку на 0x%02X (дефолт iarduino 0x%02X)", addr, TREMA_EC_ADDR);
            found = true;
            break;
        }
        if (!found) {
            ESP_LOGW(TAG, "Trema EC: Flash-I²C TDS/EC не найден; следующий полный поиск через 10 с");
            last_error = TREMA_EC_ERROR_I2C;
            s_init_backoff_until_tick = xTaskGetTickCount() + pdMS_TO_TICKS(10000);
            return false;
        }
    }

    /* Как `valVers = data[1]` в `iarduino_I2C_TDS::_begin` до вызова `reset()`. */
    s_module_fw_version = id4[1];

    /* iarduino: delay(5) после фиксации адреса перед финальной валидацией/reset. */
    vTaskDelay(pdMS_TO_TICKS(5));

    if (!trema_ec_module_reset()) {
        ESP_LOGW(TAG, "Trema EC: reset (как в iarduino_I2C_TDS::_begin) не подтвердился по REG_FLAGS_0 — продолжаем");
    }
    vTaskDelay(pdMS_TO_TICKS(5));

    sensor_initialized = true;
    use_stub_values = false;
    last_error = TREMA_EC_ERROR_NONE;
    s_init_backoff_until_tick = 0;
    ESP_LOGI(TAG, "Trema EC OK: bus %d, addr 0x%02X", (int)TREMA_EC_I2C_BUS, s_ec_i2c_addr);
    ok = true;

    return ok;
}

bool trema_ec_init(void)
{
    trema_ec_mutex_take();
    bool ok = trema_ec_init_locked();
    trema_ec_mutex_give();
    return ok;
}

bool trema_ec_read(float *ec)
{
    if (ec == NULL) {
        trema_ec_mutex_take();
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        if (!trema_ec_init_locked()) {
            ESP_LOGD(TAG, "EC sensor not connected, returning stub value");
            *ec = stub_ec;
            use_stub_values = true;
            last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
            trema_ec_mutex_give();
            return false;
        }
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", (int)TREMA_EC_I2C_BUS);
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_EC, data, 2, 1000)) {
        s_last_ec_reg_u16_valid = false;
        ESP_LOGD(TAG, "EC sensor read failed (до %d I²C-попыток на пакет), returning stub value",
                 TREMA_EC_I2C_XFER_MAX_TRIES);
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_I2C;

#ifdef __has_include
#if __has_include("diagnostics.h")
#include "diagnostics.h"
        if (diagnostics_is_initialized()) {
            diagnostics_update_sensor_metrics("ec_sensor", false);
        }
#endif
#endif

        trema_ec_mutex_give();
        return false;
    }

    uint16_t ec_raw = ((uint16_t)data[1] << 8) | data[0];
    s_last_ec_reg_u16 = ec_raw;
    s_last_ec_reg_u16_valid = true;
    *ec = (float)ec_raw * 0.001f;

    if (*ec < 0.0f || *ec > TREMA_EC_EC_REGISTER_MAX_MSCM) {
        ESP_LOGW(TAG, "Invalid EC value: %.3f mS/cm (ожидается 0…%.3f), using stub value", *ec,
                 (double)TREMA_EC_EC_REGISTER_MAX_MSCM);
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    use_stub_values = false;
    last_error = TREMA_EC_ERROR_NONE;

#ifdef __has_include
#if __has_include("diagnostics.h")
#include "diagnostics.h"
    if (diagnostics_is_initialized()) {
        diagnostics_update_sensor_metrics("ec_sensor", true);
    }
#endif
#endif

    trema_ec_mutex_give();
    return true;
}

bool trema_ec_calibrate(uint8_t stage, uint16_t known_tds)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if ((stage != 1 && stage != 2) || known_tds > 10000) {
        ESP_LOGW(TAG, "Invalid calibration parameters");
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    uint8_t reg_known_tds = REG_TDS_KNOWN_TDS;
    uint8_t tds_data[2] = {
        known_tds & 0x00FF,
        (known_tds >> 8) & 0x00FF
    };

    if (!trema_ec_write_reg(s_ec_i2c_addr, reg_known_tds, tds_data, 2, 1000)) {
        ESP_LOGW(TAG, "Failed to write known TDS value after retries");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    uint8_t reg_cal = REG_TDS_CALIBRATION;
    uint8_t cal_cmd = (stage == 1 ? TDS_BIT_CALC_1 : TDS_BIT_CALC_2) | TDS_CODE_CALC_SAVE;

    if (!trema_ec_write_reg(s_ec_i2c_addr, reg_cal, &cal_cmd, 1, 1000)) {
        ESP_LOGW(TAG, "Failed to send calibration command after retries");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    ESP_LOGI(TAG, "Calibration stage %d started with TDS %u ppm", stage, known_tds);
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

/**
 * Стадия калибровки под удержанным mutex (без вложенного `trema_ec_get_calibration` — избегаем двойного lock).
 * @see iarduino_I2C_TDS::getCalibration
 */
static uint8_t trema_ec_get_calibration_locked(uint8_t *info_out)
{
    if (info_out != NULL) {
        *info_out = 0;
    }

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        return 0;
    }

    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_CALIBRATION, data, 1, 1000)) {
        ESP_LOGW(TAG, "Failed to read calibration status after retries");
        last_error = TREMA_EC_ERROR_I2C;
        if (info_out != NULL) {
            *info_out = 0;
        }
        return 0;
    }

    if (info_out != NULL) {
        *info_out = (uint8_t)((data[0] & TDS_BITS_CALC_INFO) >> 2);
    }

    if (data[0] & TDS_FLG_STATUS_1) {
        last_error = TREMA_EC_ERROR_NONE;
        return 1;
    }
    if (data[0] & TDS_FLG_STATUS_2) {
        last_error = TREMA_EC_ERROR_NONE;
        return 2;
    }
    if (data[0] & TDS_BIT_CALC_ERR) {
        last_error = TREMA_EC_ERROR_NONE;
        return 3;
    }

    last_error = TREMA_EC_ERROR_NONE;
    return 0;
}

uint8_t trema_ec_get_calibration(uint8_t *info_out)
{
    uint8_t r;

    trema_ec_mutex_take();
    r = trema_ec_get_calibration_locked(info_out);
    trema_ec_mutex_give();
    return r;
}

uint8_t trema_ec_get_calibration_status(void)
{
    uint8_t r;

    trema_ec_mutex_take();
    r = trema_ec_get_calibration_locked(NULL);
    trema_ec_mutex_give();
    return r;
}

bool trema_ec_set_temperature(float temperature)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if (temperature < 0.0f || temperature > 63.75f) {
        ESP_LOGW(TAG, "Invalid temperature: %.2f C", temperature);
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    uint8_t temp_reg = (uint8_t)(temperature * 4.0f);
    uint8_t reg_temp = REG_TDS_t;
    if (!trema_ec_write_reg(s_ec_i2c_addr, reg_temp, &temp_reg, 1, 1000)) {
        ESP_LOGW(TAG, "Failed to set temperature after retries");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    ESP_LOGD(TAG, "Temperature set to %.2f C", temperature);
    last_temperature_c = temperature;
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

bool trema_ec_get_temperature(float *temperature)
{
    if (temperature == NULL) {
        trema_ec_mutex_take();
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    uint8_t reg_temp = REG_TDS_t;
    if (!trema_ec_read_reg(s_ec_i2c_addr, reg_temp, data, 1, 1000)) {
        ESP_LOGW(TAG, "Failed to read temperature after retries");
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    float temp_c = (float)data[0] / 4.0f;
    if (temp_c < 0.0f || temp_c > 63.75f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    *temperature = temp_c;
    last_temperature_c = temp_c;
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

uint16_t trema_ec_get_tds(void)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return stub_tds;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return stub_tds;
    }

    uint8_t reg_tds = REG_TDS_TDS;
    if (!trema_ec_read_reg(s_ec_i2c_addr, reg_tds, data, 2, 1000)) {
        ESP_LOGD(TAG, "TDS sensor read failed after %d tries, using stub values", TREMA_EC_I2C_XFER_MAX_TRIES);
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return stub_tds;
    }

    last_error = TREMA_EC_ERROR_NONE;
    uint16_t tds = ((uint16_t)data[1] << 8) | data[0];
    trema_ec_mutex_give();
    return tds;
}

float trema_ec_get_conductivity(void)
{
    float ec;
    if (trema_ec_read(&ec)) {
        return ec;
    }
    return stub_ec;
}

bool trema_ec_is_using_stub_values(void)
{
    bool v = false;
    trema_ec_mutex_take();
    v = use_stub_values;
    trema_ec_mutex_give();
    return v;
}

trema_ec_error_t trema_ec_get_error(void)
{
    trema_ec_error_t e;
    trema_ec_mutex_take();
    e = last_error;
    trema_ec_mutex_give();
    return e;
}

uint8_t trema_ec_get_i2c_address(void)
{
    uint8_t a;
    trema_ec_mutex_take();
    a = s_ec_i2c_addr;
    trema_ec_mutex_give();
    return a;
}

bool trema_ec_get_last_ec_register_raw(uint16_t *out_u16)
{
    if (out_u16 == NULL) {
        return false;
    }
    bool ok = false;
    trema_ec_mutex_take();
    if (s_last_ec_reg_u16_valid) {
        *out_u16 = s_last_ec_reg_u16;
        ok = true;
    }
    trema_ec_mutex_give();
    return ok;
}

bool trema_ec_probe_present(void)
{
    bool present = false;
    uint8_t m = 0;

    trema_ec_mutex_take();

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return false;
    }

    if (trema_ec_read_reg(s_ec_i2c_addr, REG_MODEL, &m, 1, 200) && m == TREMA_EC_DEF_MODEL_TDS) {
        present = true;
    } else {
        /* Полный перебор только в `trema_ec_init_locked` (как iarduino). Здесь — типичные адреса Trema EC, без 126
         * чтений на каждый кадр OLED (`ec_node_tasks`). */
        static const uint8_t k_probe_try_addrs[] = { 0x08U, TREMA_EC_ADDR, 0x0AU };
        for (size_t i = 0; i < sizeof(k_probe_try_addrs) / sizeof(k_probe_try_addrs[0]); i++) {
            uint8_t addr = k_probe_try_addrs[i];
            if (addr == s_ec_i2c_addr) {
                continue;
            }
            if (!trema_ec_read_model_at_addr(addr, &m, 60)) {
                continue;
            }
            if (m == TREMA_EC_DEF_MODEL_TDS) {
                present = true;
                break;
            }
        }
    }

    trema_ec_mutex_give();
    return present;
}

/* --- Полный API как в iarduino_I2C_TDS 1.3.3 (`reference/.../iarduino_I2C_TDS.cpp`); каждая функция: mutex → I²C → mutex. --- */

uint8_t trema_ec_get_module_firmware_version(void)
{
    uint8_t v;
    trema_ec_mutex_take();
    v = s_module_fw_version;
    trema_ec_mutex_give();
    return v;
}

bool trema_ec_reset_device(void)
{
    bool ok;
    trema_ec_mutex_take();
    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    ok = trema_ec_module_reset();
    last_error = ok ? TREMA_EC_ERROR_NONE : TREMA_EC_ERROR_I2C;
    trema_ec_mutex_give();
    return ok;
}

bool trema_ec_change_address(uint8_t new_addr_7bit)
{
    uint8_t new_addr = new_addr_7bit;

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if (new_addr > 0x7FU) {
        new_addr = (uint8_t)(new_addr >> 1);
    }
    if (new_addr == 0x00U || new_addr == 0x7FU) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_BITS_0, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    data[0] = (uint8_t)((data[0] & (uint8_t)~0x08U) | 0x02U);
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_BITS_0, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = (uint8_t)((new_addr << 1) | 0x01U);
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_ADDRESS, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(200));

    uint8_t id_new[4];
    if (!trema_ec_read_reg(new_addr, REG_MODEL, id_new, sizeof(id_new), 200) ||
        !trema_ec_validate_id_block(new_addr, id_new)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    s_ec_i2c_addr = new_addr;
    last_error = TREMA_EC_ERROR_NONE;
    ESP_LOGI(TAG, "Trema EC: адрес сменён на 0x%02X (@see iarduino_I2C_TDS::changeAddress)", new_addr);
    trema_ec_mutex_give();
    return true;
}

bool trema_ec_get_pull_i2c(void)
{
    bool up = false;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return false;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_FLAGS_0, data, 2, 200)) {
        trema_ec_mutex_give();
        return false;
    }
    if ((data[0] & TREMA_EC_FLG_I2C_UP) == 0) {
        trema_ec_mutex_give();
        return false;
    }
    if ((data[1] & TREMA_EC_BIT_SET_I2C_UP) == 0) {
        trema_ec_mutex_give();
        return false;
    }
    up = true;
    trema_ec_mutex_give();
    return up;
}

bool trema_ec_set_pull_i2c(bool enable)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_FLAGS_0, data, 2, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if ((data[0] & TREMA_EC_FLG_I2C_UP) == 0) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    if (enable) {
        data[0] = (uint8_t)(data[1] | TREMA_EC_BIT_SET_I2C_UP);
    } else {
        data[0] = (uint8_t)(data[1] & (uint8_t)~TREMA_EC_BIT_SET_I2C_UP);
    }

    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_BITS_0, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(50));
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

uint16_t trema_ec_get_frequency_hz(void)
{
    uint16_t hz = 0;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_FREQUENCY_L, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0;
    }
    hz = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    trema_ec_mutex_give();
    return hz;
}

bool trema_ec_set_frequency_hz(uint16_t frequency_hz)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (frequency_hz < 50U || frequency_hz > 5000U) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = TDS_CODE_CALC_SAVE;
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_CALIBRATION, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = (uint8_t)(frequency_hz & 0x00FFU);
    data[1] = (uint8_t)((frequency_hz >> 8) & 0x00FFU);
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_FREQUENCY_L, data, 2, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(50));
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

uint16_t trema_ec_get_known_tds(uint8_t stage_1_or_2)
{
    uint16_t ppm = 0;
    uint8_t reg;

    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0;
    }
    if (stage_1_or_2 < 1U || stage_1_or_2 > 2U) {
        trema_ec_mutex_give();
        return 0;
    }

    reg = (stage_1_or_2 == 1U) ? REG_TDS_KNOWN_TDS_1 : REG_TDS_KNOWN_TDS_2;
    if (!trema_ec_read_reg(s_ec_i2c_addr, reg, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0;
    }
    ppm = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    trema_ec_mutex_give();
    return ppm;
}

bool trema_ec_set_known_tds(uint8_t stage_1_or_2, uint16_t tds_ppm)
{
    uint8_t reg;

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (stage_1_or_2 < 1U || stage_1_or_2 > 2U || tds_ppm > 10000U) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = TDS_CODE_CALC_SAVE;
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_CALIBRATION, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = (uint8_t)(tds_ppm & 0x00FFU);
    data[1] = (uint8_t)((tds_ppm >> 8) & 0x00FFU);
    reg = (stage_1_or_2 == 1U) ? REG_TDS_KNOWN_TDS_1 : REG_TDS_KNOWN_TDS_2;
    if (!trema_ec_write_reg(s_ec_i2c_addr, reg, data, 2, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(50));
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

float trema_ec_get_ka(void)
{
    float ka = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Ka, data, 3, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint32_t u = ((uint32_t)data[2] << 16) | ((uint32_t)data[1] << 8) | (uint32_t)data[0];
        ka = (float)u / 10.0f;
    }
    trema_ec_mutex_give();
    return ka;
}

bool trema_ec_set_ka(float ka)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (ka < 0.01f || ka > 1677721.5f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = TDS_CODE_CALC_SAVE;
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_CALIBRATION, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    {
        uint32_t u = (uint32_t)(ka * 10.0f);
        data[0] = (uint8_t)(u & 0xFFU);
        data[1] = (uint8_t)((u >> 8) & 0xFFU);
        data[2] = (uint8_t)((u >> 16) & 0xFFU);
    }
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_Ka, data, 3, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(50));
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

float trema_ec_get_kb(void)
{
    float kb = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Kb, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint16_t u = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
        kb = (float)u / -1000.0f;
    }
    trema_ec_mutex_give();
    return kb;
}

bool trema_ec_set_kb(float kb)
{
    float v = kb;

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    if (v < 0.0f) {
        v = -v;
    }
    if (v < 0.01f || v > 65.535f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = TDS_CODE_CALC_SAVE;
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_CALIBRATION, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    {
        uint16_t u = (uint16_t)(v * 1000.0f);
        data[0] = (uint8_t)(u & 0xFFU);
        data[1] = (uint8_t)((u >> 8) & 0xFFU);
    }
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_Kb, data, 2, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(50));
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

float trema_ec_get_kt(void)
{
    float kt = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Kt, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint16_t u = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
        kt = (float)u / 10000.0f;
    }
    trema_ec_mutex_give();
    return kt;
}

bool trema_ec_set_kt(float kt)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (kt < 0.0f || kt > 6.5535f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    {
        uint16_t u = (uint16_t)(kt * 10000.0f);
        data[0] = (uint8_t)(u & 0xFFU);
        data[1] = (uint8_t)((u >> 8) & 0xFFU);
    }
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_Kt, data, 2, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

float trema_ec_get_kp(void)
{
    float kp = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Kp, data, 1, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    kp = (float)data[0] / 100.0f;
    trema_ec_mutex_give();
    return kp;
}

bool trema_ec_set_kp(float kp)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (kp < 0.01f || kp > 2.55f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = (uint8_t)(kp * 100.0f);
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_Kp, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

float trema_ec_get_reference_temperature_c(void)
{
    float t = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_T, data, 1, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    t = (float)data[0] / 4.0f;
    trema_ec_mutex_give();
    return t;
}

bool trema_ec_set_reference_temperature_c(float temperature_c)
{
    trema_ec_mutex_take();

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        trema_ec_mutex_give();
        return false;
    }
    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }
    if (temperature_c < 0.0f || temperature_c > 63.75f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        trema_ec_mutex_give();
        return false;
    }

    data[0] = (uint8_t)(temperature_c * 4.0f);
    if (!trema_ec_write_reg(s_ec_i2c_addr, REG_TDS_T, data, 1, 200)) {
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

uint32_t trema_ec_get_ro_ohm(void)
{
    uint32_t ro = 0;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Ro, data, 3, 200)) {
        trema_ec_mutex_give();
        return 0;
    }
    ro = ((uint32_t)data[2] << 16) | ((uint32_t)data[1] << 8) | (uint32_t)data[0];
    trema_ec_mutex_give();
    return ro;
}

float trema_ec_get_vout_volts(void)
{
    float v = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_Vout, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint16_t u = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
        v = (float)u / 10000.0f;
    }
    trema_ec_mutex_give();
    return v;
}

float trema_ec_get_S_mScm(void)
{
    float s = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_S, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint16_t u = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
        s = (float)u / 1000.0f;
    }
    trema_ec_mutex_give();
    return s;
}

float trema_ec_get_ec_register_mScm(void)
{
    float ec = 0.0f;
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    if (!trema_ec_read_reg(s_ec_i2c_addr, REG_TDS_EC, data, 2, 200)) {
        trema_ec_mutex_give();
        return 0.0f;
    }
    {
        uint16_t u = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
        ec = (float)u / 1000.0f;
    }
    trema_ec_mutex_give();
    return ec;
}
