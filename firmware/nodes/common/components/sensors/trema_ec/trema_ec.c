/**
 * @file trema_ec.c
 * @brief Драйвер Trema EC (iarduino) — I²C на шине ec_node (см. `TREMA_EC_I2C_BUS`)
 *
 * ec_node: Trema EC на **отдельной шине I2C_BUS_1** (GPIO по `ec_node_defaults.h`, как у pH на ph_node).
 * Шина 0 — OLED/INA209; см. `ec_node_defaults.h` и README ec_node.
 *
 * Потокобезопасность: рекурсивный mutex (как trema_ph) — MQTT/telemetry и task_sensors
 * не должны пересекаться по I²C без сериализации.
 */

#include "trema_ec.h"
#include "i2c_bus.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <math.h>

static const char *TAG = "trema_ec";

/** Ожидаемый байт регистра REG_MODEL для Trema EC (iarduino `DEF_MODEL_TDS`). */
#define TREMA_EC_EXPECTED_MODEL_ID 0x19U

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

/** Верхняя граница перебора 7-bit адреса при поиске (как цикл 1..126 в iarduino_I2C_TDS::_begin). */
#define TREMA_EC_ADDR_PROBE_END 0x77U

static SemaphoreHandle_t s_ec_mutex;

static void trema_ec_mutex_take(void)
{
    if (s_ec_mutex == NULL) {
        s_ec_mutex = xSemaphoreCreateRecursiveMutex();
        if (s_ec_mutex == NULL) {
            static bool s_mutex_fail_logged;
            if (!s_mutex_fail_logged) {
                ESP_LOGE(TAG, "recursive mutex create failed");
                s_mutex_fail_logged = true;
            }
        }
    }
    if (s_ec_mutex != NULL) {
        (void)xSemaphoreTakeRecursive(s_ec_mutex, portMAX_DELAY);
    }
}

static void trema_ec_mutex_give(void)
{
    if (s_ec_mutex != NULL) {
        xSemaphoreGiveRecursive(s_ec_mutex);
    }
}

static bool use_stub_values = false;
static float stub_ec = 1.2f;
static uint16_t stub_tds = 800;
static trema_ec_error_t last_error = TREMA_EC_ERROR_NONE;
static float last_temperature_c = NAN;
static uint8_t data[4];
static bool sensor_initialized = false;

bool trema_ec_is_initialized(void)
{
    return sensor_initialized;
}

static bool trema_ec_read_model_at_addr(uint8_t addr, uint8_t *model_out, uint32_t timeout_ms)
{
    uint8_t reg_model = REG_MODEL;
    esp_err_t err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, addr, &reg_model, 1, model_out, 1, timeout_ms);
    return (err == ESP_OK);
}

static bool trema_ec_read_reg(uint8_t addr, uint8_t reg, uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    return (i2c_bus_read_bus(TREMA_EC_I2C_BUS, addr, &reg, 1, buf, len, timeout_ms) == ESP_OK);
}

static bool trema_ec_write_reg(uint8_t addr, uint8_t reg, const uint8_t *buf, size_t len, uint32_t timeout_ms)
{
    return (i2c_bus_write_bus(TREMA_EC_I2C_BUS, addr, &reg, 1, buf, len, timeout_ms) == ESP_OK);
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
    if (d[0] != TREMA_EC_EXPECTED_MODEL_ID) {
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

bool trema_ec_init(void)
{
    trema_ec_mutex_take();
    bool ok = false;

    if (sensor_initialized) {
        ok = true;
        goto out;
    }

    if (s_init_backoff_until_tick != 0 && xTaskGetTickCount() < s_init_backoff_until_tick) {
        last_error = TREMA_EC_ERROR_I2C;
        goto out;
    }

    if (!i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        ESP_LOGE(TAG, "I²C bus %d не инициализирован (Trema EC на ec_node — шина 1, см. ec_node_defaults.h)",
                 (int)TREMA_EC_I2C_BUS);
        last_error = TREMA_EC_ERROR_I2C;
        goto out;
    }

    s_ec_i2c_addr = TREMA_EC_ADDR;
    uint8_t model = 0;
    uint8_t id4[4];
    bool found = false;

    if (trema_ec_read_model_at_addr(s_ec_i2c_addr, &model, 500) && model == TREMA_EC_EXPECTED_MODEL_ID) {
        if (trema_ec_read_reg(s_ec_i2c_addr, REG_MODEL, id4, sizeof(id4), 200) &&
            trema_ec_validate_id_block(s_ec_i2c_addr, id4)) {
            found = true;
        }
    }

    if (!found) {
        if (model == TREMA_EC_EXPECTED_MODEL_ID) {
            ESP_LOGW(TAG, "Trema EC: model 0x19 на 0x%02X, но блок ID (4 B с 0x04) не совпал — перебор 0x08–0x%02X",
                     s_ec_i2c_addr, TREMA_EC_ADDR_PROBE_END);
        } else {
            ESP_LOGW(TAG, "Trema EC: нет валидного ответа на 0x%02X, перебор 0x08–0x%02X (bus %d)",
                     s_ec_i2c_addr, TREMA_EC_ADDR_PROBE_END, (int)TREMA_EC_I2C_BUS);
        }

        for (uint8_t addr = 0x08; addr <= TREMA_EC_ADDR_PROBE_END; addr++) {
            if (!trema_ec_read_model_at_addr(addr, &model, 60)) {
                continue;
            }
            if (model != TREMA_EC_EXPECTED_MODEL_ID) {
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
            goto out;
        }
    }

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

out:
    trema_ec_mutex_give();
    return ok;
}

bool trema_ec_read(float *ec)
{
    if (ec == NULL) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    trema_ec_mutex_take();

    if (!sensor_initialized) {
        if (!trema_ec_init()) {
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

    uint8_t reg_ec = REG_TDS_EC;
    esp_err_t err = ESP_ERR_NOT_FOUND;

    if (i2c_cache_is_initialized()) {
        err = i2c_cache_get(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_ec, 1, data, 2, 500);
        if (err == ESP_OK) {
            ESP_LOGD(TAG, "EC value retrieved from cache");
        }
    }

    if (err != ESP_OK) {
        err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_ec, 1, data, 2, 1000);
        if (err == ESP_OK && i2c_cache_is_initialized()) {
            i2c_cache_put(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_ec, 1, data, 2, 500);
        }
    }

    if (err != ESP_OK) {
        ESP_LOGD(TAG, "EC sensor read failed: %s, returning stub value", esp_err_to_name(err));
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
    *ec = (float)ec_raw * 0.001f;

    if (*ec < 0.0f || *ec > 10.0f) {
        ESP_LOGW(TAG, "Invalid EC value: %.3f mS/cm, using stub value", *ec);
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

    esp_err_t err = i2c_bus_write_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_known_tds, 1, tds_data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write known TDS value: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(10));

    uint8_t reg_cal = REG_TDS_CALIBRATION;
    uint8_t cal_cmd = (stage == 1 ? TDS_BIT_CALC_1 : TDS_BIT_CALC_2) | TDS_CODE_CALC_SAVE;

    err = i2c_bus_write_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_cal, 1, &cal_cmd, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send calibration command: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        trema_ec_mutex_give();
        return false;
    }

    ESP_LOGI(TAG, "Calibration stage %d started with TDS %u ppm", stage, known_tds);
    last_error = TREMA_EC_ERROR_NONE;
    trema_ec_mutex_give();
    return true;
}

uint8_t trema_ec_get_calibration_status(void)
{
    trema_ec_mutex_take();

    if (!sensor_initialized || !i2c_bus_is_initialized_bus(TREMA_EC_I2C_BUS)) {
        trema_ec_mutex_give();
        return 0;
    }

    uint8_t reg_cal = REG_TDS_CALIBRATION;
    esp_err_t err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_cal, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration status: %s", esp_err_to_name(err));
        trema_ec_mutex_give();
        return 0;
    }

    uint8_t status = 0;
    if (data[0] & 0x40) {
        status = 1;
    } else if (data[0] & 0x80) {
        status = 2;
    }

    trema_ec_mutex_give();
    return status;
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
    esp_err_t err = i2c_bus_write_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_temp, 1, &temp_reg, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set temperature: %s", esp_err_to_name(err));
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
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
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
    esp_err_t err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_temp, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read temperature: %s", esp_err_to_name(err));
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
    esp_err_t err = i2c_bus_read_bus(TREMA_EC_I2C_BUS, s_ec_i2c_addr, &reg_tds, 1, data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "TDS sensor read failed: %s, using stub values", esp_err_to_name(err));
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
    return use_stub_values;
}

trema_ec_error_t trema_ec_get_error(void)
{
    return last_error;
}

uint8_t trema_ec_get_i2c_address(void)
{
    return s_ec_i2c_addr;
}
