/**
 * @file trema_ph.c
 * @brief Реализация драйвера Trema pH-сенсора
 *
 * Протокол и проверка заголовка приведены к iarduino_I2C_pH v1.2.3
 * (чтение 4 байт с REG_MODEL: MODEL, VERSION, ADDRESS, CHIP_ID).
 * После проверки, как в iarduino_I2C_pH::_begin(), выполняется программный reset
 * (регистр REG_BITS_0 бит 0x80 → ожидание REG_FLAGS_0 бит 0x80).
 */

#include "trema_ph.h"
#include "i2c_bus.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_rom_sys.h"
#include <stddef.h>
#include <stdio.h>

static const char *TAG = "trema_ph";

/** 7-bit адрес на шине (можно сменить через trema_ph_set_i2c_address; init перебирает 0x0A/0x09) */
static uint8_t s_ph_i2c_addr_7bit = TREMA_PH_ADDR;

static bool trema_ph_addr_valid(uint8_t a)
{
    return a >= 0x08 && a <= 0x77;
}

void trema_ph_set_i2c_address(uint8_t addr_7bit)
{
    if (trema_ph_addr_valid(addr_7bit)) {
        s_ph_i2c_addr_7bit = addr_7bit;
        ESP_LOGI(TAG, "pH I2C 7-bit address set to 0x%02X", s_ph_i2c_addr_7bit);
    } else {
        ESP_LOGW(TAG, "pH I2C address 0x%02X ignored (must be 0x08..0x77)", addr_7bit);
    }
}

uint8_t trema_ph_get_i2c_address(void)
{
    return s_ph_i2c_addr_7bit;
}

/** true — шаги чтения дублировать в ESP_LOGI (для отладки без смены уровня тега) */
static bool s_read_trace_verbose = false;

/** Трассировка шагов чтения: INFO если verbose, иначе DEBUG */
#define TREMA_TRACE_READ(fmt, ...)                                                     \
    do {                                                                                \
        if (s_read_trace_verbose) {                                                    \
            ESP_LOGI(TAG, "[pH read] " fmt, ##__VA_ARGS__);                            \
        } else {                                                                        \
            ESP_LOGD(TAG, "[pH read] " fmt, ##__VA_ARGS__);                            \
        }                                                                               \
    } while (0)

#define TREMA_TRACE_INIT(fmt, ...)                                                    \
    do {                                                                                \
        if (s_read_trace_verbose) {                                                    \
            ESP_LOGI(TAG, "[pH init] " fmt, ##__VA_ARGS__);                           \
        } else {                                                                        \
            ESP_LOGD(TAG, "[pH init] " fmt, ##__VA_ARGS__);                           \
        }                                                                               \
    } while (0)

void trema_ph_set_read_trace_verbose(bool verbose)
{
    s_read_trace_verbose = verbose;
    ESP_LOGI(TAG, "pH I2C trace: verbose=%s (steps [pH read]/[pH init]: %s)", verbose ? "true" : "false",
             verbose ? "ESP_LOGI" : "ESP_LOGD — включите: esp_log_level_set(\"trema_ph\", ESP_LOG_DEBUG)");
}

/** Сериализация доступа: task_sensors и telemetry_cb MQTT могут вызывать trema_ph_* одновременно */
static SemaphoreHandle_t s_trema_mutex;

static void trema_ph_mutex_take(void)
{
    if (s_trema_mutex == NULL) {
        s_trema_mutex = xSemaphoreCreateRecursiveMutex();
        if (s_trema_mutex == NULL) {
            static bool s_mutex_fail_logged;
            if (!s_mutex_fail_logged) {
                ESP_LOGE(TAG, "recursive mutex create failed (out of heap?) — trema_ph без защиты от гонок");
                s_mutex_fail_logged = true;
            }
        }
    }
    if (s_trema_mutex != NULL) {
        (void)xSemaphoreTakeRecursive(s_trema_mutex, portMAX_DELAY);
    }
}

static void trema_ph_mutex_give(void)
{
    if (s_trema_mutex != NULL) {
        xSemaphoreGiveRecursive(s_trema_mutex);
    }
}

/** Как iarduino_I2C_pH.h: REG_FLAGS_0 / REG_BITS_0 */
#define TREMA_PH_REG_FLAGS_0 0x00
#define TREMA_PH_REG_BITS_0  0x01

#define TREMA_PH_I2C_IO_RETRIES 10

/** Повторы чтения pH при отказе: вне диапазона / 0xFFFF / STAB_ERR при «летающем» сыром значении */
#define TREMA_PH_SAMPLE_ATTEMPTS       4
#define TREMA_PH_SAMPLE_RETRY_DELAY_MS 80U
/** Макс. REG_PH_pH в тысячных для 14.000 pH (iarduino) */
#define TREMA_PH_RAW_THOUSANDTHS_MAX   14000U

// Stub values for when sensor is not connected
static bool use_stub_values = false;
static float stub_ph = 6.5f;  // Neutral pH

static bool s_i2c_logs_suppressed = false;
static bool s_missing_reported = false;
static esp_err_t s_last_missing_err = ESP_OK;

// Buffer for I2C communication
static uint8_t data[4];

// Sensor initialization flag
static bool sensor_initialized = false;

static void trema_ph_suppress_i2c_logs(void)
{
    if (s_i2c_logs_suppressed) {
        return;
    }

    // Убираем спам от esp-idf i2c.master, оставляем верхнеуровневые сообщения
    esp_log_level_set("i2c.master", ESP_LOG_NONE);
    s_i2c_logs_suppressed = true;
}

static void trema_ph_report_missing(esp_err_t err)
{
    if (!s_missing_reported || err != s_last_missing_err) {
        ESP_LOGW(TAG, "pH sensor not connected (err=%s, code=0x%x)", esp_err_to_name(err), err);
        s_missing_reported = true;
        s_last_missing_err = err;
    }
}

static esp_err_t trema_ph_read_error_byte(uint8_t *err_byte)
{
    uint8_t reg = REG_PH_ERROR;
    return i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg, 1, err_byte, 1, 1000);
}

static esp_err_t trema_ph_read_registers(uint8_t start_reg, uint8_t *out, size_t len)
{
    esp_err_t last_err = ESP_ERR_INVALID_RESPONSE;
    ESP_LOGD(TAG, "[I2C] read start: bus=1 addr=0x%02X reg=0x%02X len=%u", s_ph_i2c_addr_7bit, start_reg, (unsigned)len);
    for (int attempt = 0; attempt < TREMA_PH_I2C_IO_RETRIES; attempt++) {
        last_err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &start_reg, 1, out, len, 1000);
        if (last_err == ESP_OK) {
            if (len <= 4U) {
                char hex[4 * 3 + 1] = {0};
                size_t p = 0;
                for (size_t i = 0; i < len && p + 3 < sizeof(hex); i++) {
                    p += (size_t)snprintf(hex + p, sizeof(hex) - p, "%02X ", out[i]);
                }
                ESP_LOGD(TAG, "[I2C] read OK reg=0x%02X attempt=%d data: %s", start_reg, attempt + 1, hex);
            } else {
                ESP_LOGD(TAG, "[I2C] read OK reg=0x%02X attempt=%d len=%u", start_reg, attempt + 1, (unsigned)len);
            }
            /* iarduino_I2C_pH::_readBytes: delayMicroseconds(500) между пакетами */
            esp_rom_delay_us(500);
            return ESP_OK;
        }
        ESP_LOGD(TAG, "[I2C] read retry reg=0x%02X attempt=%d/%d err=%s (0x%x)", start_reg, attempt + 1,
                 TREMA_PH_I2C_IO_RETRIES, esp_err_to_name(last_err), last_err);
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    ESP_LOGW(TAG, "[I2C] read FAIL bus=1 addr=0x%02X reg=0x%02X len=%u after %d tries: %s (0x%x)", s_ph_i2c_addr_7bit,
             start_reg, (unsigned)len, TREMA_PH_I2C_IO_RETRIES, esp_err_to_name(last_err), last_err);
    return last_err;
}

static void trema_ph_invalidate_ph_read_cache(void)
{
    if (!i2c_cache_is_initialized()) {
        ESP_LOGD(TAG, "[cache] skip invalidate: cache off");
        return;
    }
    uint8_t reg_ph = REG_PH_pH;
    (void)i2c_cache_invalidate(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1);
    ESP_LOGD(TAG, "[cache] invalidated key bus=1 addr=0x%02X reg=0x%02X", s_ph_i2c_addr_7bit, reg_ph);
}

/**
 * Программная перезагрузка модуля (iarduino_I2C_pH::reset).
 * Не зависит от sensor_initialized — вызывается из trema_ph_init до установки флага.
 */
static bool trema_ph_soft_reset_hw(void)
{
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGW(TAG, "[soft reset] bus 1 not initialized");
        return false;
    }

    TREMA_TRACE_INIT("soft reset: read REG_BITS_0 (0x%02X)", TREMA_PH_REG_BITS_0);
    uint8_t reg_bits = TREMA_PH_REG_BITS_0;

    esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_bits, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "pH soft reset: read REG_BITS_0 failed: %s", esp_err_to_name(err));
        return false;
    }
    TREMA_TRACE_INIT("soft reset: REG_BITS_0 before OR=0x%02X", data[0]);
    /* как пауза между операциями _readBytes/_writeBytes в iarduino */
    esp_rom_delay_us(500);

    uint8_t reset_value = data[0] | 0x80U;
    err = i2c_bus_write_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_bits, 1, &reset_value, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "pH soft reset: write REG_BITS_0 failed: %s", esp_err_to_name(err));
        return false;
    }
    TREMA_TRACE_INIT("soft reset: wrote REG_BITS_0=0x%02X, delay 10ms", reset_value);

    vTaskDelay(pdMS_TO_TICKS(10));

    uint8_t reg_flags = TREMA_PH_REG_FLAGS_0;
    for (int poll = 0; poll < 100; poll++) {
        err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_flags, 1, data, 1, 500);
        if (err == ESP_OK && (data[0] & 0x80U) != 0) {
            TREMA_TRACE_INIT("soft reset: REG_FLAGS_0=0x%02X reset done (poll %d)", data[0], poll + 1);
            trema_ph_invalidate_ph_read_cache();
            return true;
        }
        if (poll % 25 == 0) {
            ESP_LOGD(TAG, "[soft reset] wait FLG_RESET poll=%d err=%s flags=0x%02X", poll,
                     err == ESP_OK ? "OK" : esp_err_to_name(err), err == ESP_OK ? data[0] : 0);
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }

    ESP_LOGW(TAG, "pH soft reset: timeout waiting for REG_FLAGS_0 completion bit");
    return false;
}

/**
 * Проверка заголовка как в iarduino_I2C_pH::_begin (model / address / chip line).
 */
static bool trema_ph_validate_module_header(const uint8_t hdr[4])
{
    if (hdr[0] != TREMA_PH_MODEL_ID) {
        ESP_LOGW(TAG, "pH header: model 0x%02X (expected 0x%02X)", hdr[0], TREMA_PH_MODEL_ID);
        return false;
    }
    if (((hdr[2] >> 1) != s_ph_i2c_addr_7bit) && (hdr[2] != 0xFF)) {
        ESP_LOGW(TAG, "pH header: address byte 0x%02X (expected match addr 0x%02X or 0xFF)", hdr[2], s_ph_i2c_addr_7bit);
        return false;
    }
    if (hdr[3] != TREMA_PH_CHIP_ID_FLASH && hdr[3] != TREMA_PH_CHIP_ID_METRO) {
        ESP_LOGW(TAG, "pH header: chip id 0x%02X (expected Flash 0x%02X or Metro 0x%02X)",
                 hdr[3], TREMA_PH_CHIP_ID_FLASH, TREMA_PH_CHIP_ID_METRO);
        return false;
    }
    return true;
}

/**
 * Чтение заголовка: сначала выбранный 7-bit адрес, затем без дубликатов 0x0A и 0x09 (примеры iarduino).
 * При успехе оставляет s_ph_i2c_addr_7bit на рабочем адресе; при полном провале восстанавливает исходный.
 */
static esp_err_t trema_ph_read_header_with_discovery(uint8_t hdr[4])
{
    const uint8_t preferred = s_ph_i2c_addr_7bit;
    uint8_t try_list[3];
    size_t n_try = 0;
    try_list[n_try++] = preferred;
    const uint8_t common[] = { 0x0A, 0x09 };
    for (size_t ci = 0; ci < 2 && n_try < 3; ci++) {
        bool dup = false;
        for (size_t j = 0; j < n_try; j++) {
            if (common[ci] == try_list[j]) {
                dup = true;
                break;
            }
        }
        if (!dup) {
            try_list[n_try++] = common[ci];
        }
    }

    esp_err_t last_err = ESP_ERR_NOT_FOUND;
    for (size_t i = 0; i < n_try; i++) {
        const uint8_t try_a = try_list[i];
        s_ph_i2c_addr_7bit = try_a;
        last_err = trema_ph_read_registers(REG_MODEL, hdr, 4);
        if (last_err != ESP_OK) {
            continue;
        }
        if (trema_ph_validate_module_header(hdr)) {
            if (try_a != preferred) {
                ESP_LOGI(TAG, "pH модуль отвечает по I²C 0x%02X (до поиска ожидали 0x%02X)", try_a, preferred);
            }
            return ESP_OK;
        }
        last_err = ESP_ERR_INVALID_RESPONSE;
    }

    s_ph_i2c_addr_7bit = preferred;
    return last_err;
}

bool trema_ph_init(void)
{
    trema_ph_mutex_take();
    bool ok = false;

    TREMA_TRACE_INIT("start");
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        trema_ph_suppress_i2c_logs();
        trema_ph_report_missing(ESP_ERR_INVALID_STATE);
        TREMA_TRACE_INIT("abort: I2C bus 1 not initialized");
        goto out;
    }

    trema_ph_suppress_i2c_logs();
    uint8_t hdr[4];
    TREMA_TRACE_INIT("read header REG_MODEL..CHIP_ID (discovery 0x%02X/0x09↔0x0A)", s_ph_i2c_addr_7bit);
    esp_err_t err = trema_ph_read_header_with_discovery(hdr);
    if (err != ESP_OK) {
        trema_ph_report_missing(err);
        TREMA_TRACE_INIT("abort: header I2C err=%s", esp_err_to_name(err));
        goto out;
    }
    TREMA_TRACE_INIT("header bytes: M=0x%02X V=0x%02X A=0x%02X C=0x%02X addr_7bit=0x%02X", hdr[0], hdr[1], hdr[2],
                     hdr[3], s_ph_i2c_addr_7bit);
    /* Как iarduino _begin(): сбрасываем модуль в дефолты; результат reset там не проверяется */
    if (!trema_ph_soft_reset_hw()) {
        ESP_LOGW(TAG, "pH sensor soft reset after probe failed (continuing init like iarduino)");
    }
    vTaskDelay(pdMS_TO_TICKS(5));
    TREMA_TRACE_INIT("post-reset delay 5ms done");

    sensor_initialized = true;
    use_stub_values = false;
    s_missing_reported = false;
    s_last_missing_err = ESP_OK;
    ESP_LOGI(TAG, "pH sensor OK (fw=%u, chip=0x%02X)", (unsigned)hdr[1], hdr[3]);
    ok = true;
out:
    trema_ph_mutex_give();
    TREMA_TRACE_INIT("finish ok=%d", ok);
    return ok;
}

bool trema_ph_read(float *ph)
{
    if (ph == NULL) {
        return false;
    }

    trema_ph_mutex_take();
    bool ok = false;
    TREMA_TRACE_READ("--- begin read ---");

    if (!sensor_initialized) {
        TREMA_TRACE_READ("sensor not init, calling trema_ph_init()");
        if (!trema_ph_init()) {
            TREMA_TRACE_READ("FAIL after init: stub ph=%.2f", (double)stub_ph);
            ESP_LOGW(TAG, "[pH read] FAIL: init failed, using stub");
            *ph = stub_ph;
            use_stub_values = true;
            goto out;
        }
        TREMA_TRACE_READ("lazy init ok");
    }

    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        trema_ph_report_missing(ESP_ERR_INVALID_STATE);
        ESP_LOGW(TAG, "[pH read] FAIL: I2C bus 1 down");
        *ph = stub_ph;
        use_stub_values = true;
        goto out;
    }

    uint8_t reg_ph = REG_PH_pH;
    uint8_t ph_bytes[2];
    esp_err_t err = ESP_ERR_NOT_FOUND;
    uint16_t last_raw = 0;
    uint8_t last_err_flags = 0;
    bool had_transport_err = false;
    esp_err_t last_xfer_err = ESP_OK;

    for (int sample_try = 0; sample_try < TREMA_PH_SAMPLE_ATTEMPTS; sample_try++) {
        if (sample_try > 0) {
            trema_ph_invalidate_ph_read_cache();
            vTaskDelay(pdMS_TO_TICKS(TREMA_PH_SAMPLE_RETRY_DELAY_MS));
            TREMA_TRACE_READ("sample retry %d/%d", sample_try + 1, TREMA_PH_SAMPLE_ATTEMPTS);
        }

        err = ESP_ERR_NOT_FOUND;
        bool cache_allowed = (sample_try == 0 && i2c_cache_is_initialized());
        bool from_cache_hit = false;

        if (cache_allowed) {
            err = i2c_cache_get(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1, ph_bytes, 2, 500);
            if (err == ESP_OK) {
                from_cache_hit = true;
                TREMA_TRACE_READ("cache HIT reg=0x%02X bytes %02X %02X", reg_ph, ph_bytes[0], ph_bytes[1]);
            } else {
                TREMA_TRACE_READ("cache MISS (%s), I2C read", esp_err_to_name(err));
            }
        } else {
            TREMA_TRACE_READ("I2C only (no cache) reg=0x%02X", reg_ph);
        }

        if (err != ESP_OK) {
            err = trema_ph_read_registers(reg_ph, ph_bytes, 2);
            from_cache_hit = false;
            if (err != ESP_OK) {
                ESP_LOGD(TAG, "[pH read] REG_PH_pH I2C err=%s (try %d)", esp_err_to_name(err), sample_try + 1);
                had_transport_err = true;
                last_xfer_err = err;
                continue;
            }
            TREMA_TRACE_READ("I2C raw %02X %02X", ph_bytes[0], ph_bytes[1]);
        }

        if (from_cache_hit) {
            /* при HIT не было trema_ph_read_registers для REG_PH — пауза перед REG_ERROR как в iarduino */
            esp_rom_delay_us(500);
        }

        uint8_t err_byte = 0;
        esp_err_t e2 = trema_ph_read_error_byte(&err_byte);
        if (e2 != ESP_OK) {
            ESP_LOGD(TAG, "[pH read] REG_PH_ERROR read err=%s (try %d)", esp_err_to_name(e2), sample_try + 1);
            had_transport_err = true;
            last_xfer_err = e2;
            continue;
        }

        uint16_t pH_raw = ((uint16_t)ph_bytes[1] << 8) | ph_bytes[0];
        last_raw = pH_raw;
        last_err_flags = err_byte;
        float ph_val = (float)pH_raw * 0.001f;
        TREMA_TRACE_READ("decode raw=0x%04X err_reg=0x%02X -> pH=%.4f", (unsigned)pH_raw, err_byte, (double)ph_val);

        bool stab_bad = (err_byte & PH_FLG_STAB_ERR) != 0;
        bool sentinel = (pH_raw == 0xFFFFU);
        bool raw_high = (pH_raw > TREMA_PH_RAW_THOUSANDTHS_MAX);

        if (sentinel) {
            ESP_LOGD(TAG, "[pH read] raw=0xFFFF (часто открытая шина/I2C); try %d", sample_try + 1);
            continue;
        }
        if (raw_high || ph_val < 0.0f || ph_val > 14.0f) {
            ESP_LOGD(TAG, "[pH read] сырое вне 0..14 pH (сырые тысячные >%u или pH=%.3f); щуп в воздухе или переходный процесс; try %d",
                     (unsigned)TREMA_PH_RAW_THOUSANDTHS_MAX, (double)ph_val, sample_try + 1);
            if (stab_bad) {
                ESP_LOGD(TAG, "[pH read] также STAB_ERR");
            }
            continue;
        }

        /* 0..14 и не 0xFFFF: допускаем при STAB_ERR (Arduino getPH не блокирует по стабильности) */
        *ph = ph_val;
        if (i2c_cache_is_initialized() && !from_cache_hit) {
            i2c_cache_put(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1, ph_bytes, 2, 500);
            TREMA_TRACE_READ("cache PUT после валидации (I2C)");
        }

        use_stub_values = false;
        s_missing_reported = false;
        s_last_missing_err = ESP_OK;
        TREMA_TRACE_READ("SUCCESS pH=%.4f", (double)*ph);
        #ifdef __has_include
            #if __has_include("diagnostics.h")
                #include "diagnostics.h"
                if (diagnostics_is_initialized()) {
                    diagnostics_update_sensor_metrics("ph_sensor", true);
                }
            #endif
        #endif
        ok = true;
        goto out;
    }

    /* Все попытки исчерпаны */
    trema_ph_invalidate_ph_read_cache();
    ESP_LOGW(TAG,
             "[pH read] FAIL после %d попыток: последний raw=0x%04X (%.3f pH) REG_PH_ERROR=0x%02X%s%s — опустите щуп в раствор, "
             "проверьте калибровку и I²C (подтяжки, длина провода)",
             TREMA_PH_SAMPLE_ATTEMPTS, (unsigned)last_raw, (double)((float)last_raw * 0.001f), last_err_flags,
             (last_err_flags & PH_FLG_STAB_ERR) ? " STAB_ERR" : "",
             (last_err_flags & PH_FLG_CALC_ERR) ? " CALC_ERR" : "");
    if (had_transport_err && last_xfer_err != ESP_OK) {
        ESP_LOGW(TAG, "[pH read] последняя ошибка I²C: %s (0x%x)", esp_err_to_name(last_xfer_err), last_xfer_err);
    }
    trema_ph_report_missing(had_transport_err && last_xfer_err != ESP_OK ? last_xfer_err : ESP_ERR_INVALID_RESPONSE);
    *ph = stub_ph;
    use_stub_values = true;
    #ifdef __has_include
        #if __has_include("diagnostics.h")
            #include "diagnostics.h"
            if (diagnostics_is_initialized()) {
                diagnostics_update_sensor_metrics("ph_sensor", false);
            }
        #endif
    #endif
out:
    trema_ph_mutex_give();
    TREMA_TRACE_READ("--- end read ok=%d ---", ok);
    return ok;
}

bool trema_ph_calibrate(uint8_t stage, float known_pH)
{
    trema_ph_mutex_take();
    bool ok = false;
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        goto out;
    }
    
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGE(TAG, "I²C bus 1 not initialized");
        goto out;
    }

    // Validate parameters
    if ((stage != 1 && stage != 2) || known_pH < 0.0f || known_pH > 14.0f) {
        ESP_LOGW(TAG, "Invalid calibration parameters");
        goto out;
    }
    
    // Write known pH value
    uint8_t reg_known_ph = REG_PH_KNOWN_PH;
    uint16_t ph_value_int = (uint16_t)(known_pH * 1000.0f);
    uint8_t ph_data[2] = {
        ph_value_int & 0x00FF,       // LSB
        (ph_value_int >> 8) & 0x00FF // MSB
    };
    
    esp_err_t err = i2c_bus_write_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_known_ph, 1, ph_data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write known pH value: %s", esp_err_to_name(err));
        goto out;
    }
    
    vTaskDelay(pdMS_TO_TICKS(10));
    
    // Send calibration command
    uint8_t reg_cal = REG_PH_CALIBRATION;
    uint8_t cal_cmd = (stage == 1 ? PH_BIT_CALC_1 : PH_BIT_CALC_2) | PH_CODE_CALC_SAVE;
    
    err = i2c_bus_write_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_cal, 1, &cal_cmd, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send calibration command: %s", esp_err_to_name(err));
        goto out;
    }

    /* iarduino _writeBytes ждёт 10 ms после каждой записи — даём модулю применить команду */
    vTaskDelay(pdMS_TO_TICKS(10));

    ESP_LOGI(TAG, "Calibration stage %d started with pH %.3f", stage, known_pH);

    /* Дождаться завершения этапа на модуле (флаги STATUS в REG_PH_CALIBRATION; см. wiki iArduino Trema pH I2C). */
    const uint32_t poll_ms = 200U;
    const uint32_t idle_giveup_ms = 5000U;
    const uint32_t max_busy_wait_ms = 45000U;
    uint32_t elapsed = 0U;
    bool saw_non_idle = false;

    while (elapsed < max_busy_wait_ms) {
        uint8_t st = trema_ph_get_calibration_status();
        if (st != 0) {
            saw_non_idle = true;
        } else if (saw_non_idle) {
            break;
        }
        if (!saw_non_idle && elapsed >= idle_giveup_ms) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(poll_ms));
        elapsed += poll_ms;
    }

    if (saw_non_idle && trema_ph_get_calibration_status() != 0) {
        ESP_LOGW(TAG, "pH cal: timeout waiting for idle after busy (stage %u)", (unsigned)stage);
        ok = false;
        goto out;
    }
    if (!saw_non_idle) {
        ESP_LOGW(TAG, "pH cal: module did not report busy flags (older firmware?); settling 2 s before result check");
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    ok = trema_ph_get_calibration_result();
    if (!ok) {
        ESP_LOGW(TAG, "pH cal: module CALC_ERR or read failed (stage %u)", (unsigned)stage);
    }
out:
    trema_ph_mutex_give();
    return ok;
}

uint8_t trema_ph_get_calibration_status(void)
{
    trema_ph_mutex_take();
    uint8_t ret = 0;
    // Check if sensor is initialized
    if (!sensor_initialized) {
        goto out;
    }
    
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }

    // Read calibration status
    uint8_t reg_cal = REG_PH_CALIBRATION;
    esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_cal, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration status: %s", esp_err_to_name(err));
        goto out;
    }
    
    if (data[0] & PH_FLG_STATUS_1) {
        ret = 1;
        goto out;
    }
    if (data[0] & PH_FLG_STATUS_2) {
        ret = 2;
    }
out:
    trema_ph_mutex_give();
    return ret;
}

bool trema_ph_get_calibration_result(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    // Check if sensor is initialized
    if (!sensor_initialized) {
        goto out;
    }
    
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }

    // Read error flags
    uint8_t reg_error = REG_PH_ERROR;
    esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_error, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration result: %s", esp_err_to_name(err));
        goto out;
    }
    
    // Return true if calibration error flag is NOT set
    ok = !(data[0] & PH_FLG_CALC_ERR);
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_get_stability(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    // Check if sensor is initialized
    if (!sensor_initialized) {
        goto out;
    }
    
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }

    // Read error flags
    uint8_t reg_error = REG_PH_ERROR;
    esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_error, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read stability status: %s", esp_err_to_name(err));
        goto out;
    }
    
    // Check if stability error flag is set
    if (data[0] & PH_FLG_STAB_ERR) {
        ESP_LOGD(TAG, "pH measurement is not stable (STAB_ERR flag set)");
        goto out;
    }
    
    // Return true if stability error flag is NOT set
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_wait_for_stable_reading(uint32_t timeout_ms)
{
    if (!sensor_initialized) {
        return false;
    }

    uint32_t elapsed_time = 0;
    const uint32_t check_interval = 100;

    while (elapsed_time < timeout_ms) {
        if (trema_ph_get_stability()) {
            return true;
        }

        vTaskDelay(pdMS_TO_TICKS(check_interval));
        elapsed_time += check_interval;
    }

    ESP_LOGW(TAG, "Timeout waiting for stable pH measurement after %u ms", (unsigned int)timeout_ms);
    return false;
}

float trema_ph_get_value(void)
{
    float ph;
    if (trema_ph_read(&ph)) {
        return ph;
    }
    return stub_ph;
}

bool trema_ph_reset(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Cannot reset uninitialized pH sensor");
        goto out;
    }

    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGE(TAG, "I²C bus 1 not initialized");
        goto out;
    }

    if (!trema_ph_soft_reset_hw()) {
        goto out;
    }

    ESP_LOGI(TAG, "pH sensor reset completed");
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_is_using_stub_values(void)
{
    return use_stub_values;
}

bool trema_ph_is_initialized(void)
{
    return sensor_initialized;
}

bool trema_ph_log_connection_status(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGW(TAG, "I²C bus 1 not initialized (pH sensor unreachable)");
        goto out;
    }

    trema_ph_suppress_i2c_logs();
    uint8_t hdr[4];
    esp_err_t err = trema_ph_read_header_with_discovery(hdr);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "I²C bus 1 -> pH модуль: нет ответа после discovery (базовый addr 0x%02X): %s", s_ph_i2c_addr_7bit,
                 esp_err_to_name(err));
        goto out;
    }

    ESP_LOGI(TAG, "I²C bus 1 -> pH module OK @7-bit 0x%02X (fw=%u chip=0x%02X)", s_ph_i2c_addr_7bit, (unsigned)hdr[1],
             hdr[3]);
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_probe_presence(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    ESP_LOGD(TAG, "[probe] start bus=1");
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGD(TAG, "[probe] abort: bus 1 not init");
        goto out;
    }
    trema_ph_suppress_i2c_logs();
    uint8_t hdr[4];
    esp_err_t e = trema_ph_read_header_with_discovery(hdr);
    if (e != ESP_OK) {
        ESP_LOGD(TAG, "[probe] discovery err=%s", esp_err_to_name(e));
        goto out;
    }
    ESP_LOGD(TAG, "[probe] hdr %02X %02X %02X %02X addr_7bit=0x%02X", hdr[0], hdr[1], hdr[2], hdr[3],
             s_ph_i2c_addr_7bit);
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}
