/**
 * @file trema_ph.c
 * @brief Trema pH I²C: порт iarduino_I2C_pH v1.2.3 на ESP-IDF + FreeRTOS
 *
 * Источник регистров и последовательностей: `reference/iarduino_I2C_pH-1.2.3/src/iarduino_I2C_pH.cpp`
 * и `iarduino_I2C_pH.h` (tremaru / iarduino.ru).
 *
 * Потокобезопасность:
 * - Recursive mutex на всех публичных entry points (вложенные вызовы из той же задачи — ОК).
 * - Lazy create mutex защищён portMUX (нет двойного xSemaphoreCreate при гонке двух задач).
 * - Очередь снимков: запись только из секции, где уже удержан mutex и завершён успешный read;
 *   `trema_ph_try_cached_measurement` берёт тот же mutex на время peek/копии (сериализация с Overwrite).
 *
 * Память: без malloc в горячем пути; mutex/queue создаёт потребитель (`xQueueCreate` в ph_node).
 */

#include "trema_ph.h"
#include "i2c_bus.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "freertos/portmacro.h"
#include "esp_rom_sys.h"
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static const char *TAG = "trema_ph";

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

static bool s_read_trace_verbose = false;

#define TREMA_TRACE_READ(fmt, ...)                                                                 \
    do {                                                                                           \
        if (s_read_trace_verbose) {                                                                \
            ESP_LOGI(TAG, "[pH read] " fmt, ##__VA_ARGS__);                                        \
        } else {                                                                                   \
            ESP_LOGD(TAG, "[pH read] " fmt, ##__VA_ARGS__);                                        \
        }                                                                                          \
    } while (0)

#define TREMA_TRACE_INIT(fmt, ...)                                                                 \
    do {                                                                                           \
        if (s_read_trace_verbose) {                                                                \
            ESP_LOGI(TAG, "[pH init] " fmt, ##__VA_ARGS__);                                        \
        } else {                                                                                   \
            ESP_LOGD(TAG, "[pH init] " fmt, ##__VA_ARGS__);                                        \
        }                                                                                          \
    } while (0)

void trema_ph_set_read_trace_verbose(bool verbose)
{
    s_read_trace_verbose = verbose;
    ESP_LOGI(TAG, "pH I2C trace: verbose=%s (steps [pH read]/[pH init]: %s)", verbose ? "true" : "false",
             verbose ? "ESP_LOGI" : "ESP_LOGD — включите: esp_log_level_set(\"trema_ph\", ESP_LOG_DEBUG)");
}

static SemaphoreHandle_t s_trema_mutex;
static portMUX_TYPE s_mutex_create_spin = portMUX_INITIALIZER_UNLOCKED;

static void trema_ph_mutex_take(void)
{
    if (s_trema_mutex == NULL) {
        portENTER_CRITICAL(&s_mutex_create_spin);
        if (s_trema_mutex == NULL) {
            SemaphoreHandle_t m = xSemaphoreCreateRecursiveMutex();
            if (m != NULL) {
                s_trema_mutex = m;
            }
        }
        portEXIT_CRITICAL(&s_mutex_create_spin);
        if (s_trema_mutex == NULL) {
            static bool s_mutex_fail_logged;
            if (!s_mutex_fail_logged) {
                ESP_LOGE(TAG, "recursive mutex create failed (heap?) — trema_ph без защиты от гонок");
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

static QueueHandle_t s_sample_q;

void trema_ph_bind_sample_queue(QueueHandle_t queue)
{
    trema_ph_mutex_take();
    s_sample_q = queue;
    trema_ph_mutex_give();
}

void trema_ph_unbind_sample_queue(void)
{
    trema_ph_mutex_take();
    s_sample_q = NULL;
    trema_ph_mutex_give();
}

bool trema_ph_try_cached_measurement(trema_ph_measurement_t *out, uint32_t max_age_ms)
{
    if (out == NULL) {
        return false;
    }
    /* Сериализация с trema_ph_read → push: не подглядывать очередь параллельно с Overwrite. */
    trema_ph_mutex_take();
    QueueHandle_t q = s_sample_q;
    if (q == NULL) {
        trema_ph_mutex_give();
        return false;
    }
    trema_ph_measurement_t tmp;
    if (xQueuePeek(q, &tmp, 0) != pdTRUE || !tmp.valid) {
        trema_ph_mutex_give();
        return false;
    }
    TickType_t age = xTaskGetTickCount() - tmp.tick_stamp;
    if (age > pdMS_TO_TICKS(max_age_ms)) {
        trema_ph_mutex_give();
        return false;
    }
    *out = tmp;
    trema_ph_mutex_give();
    return true;
}

static void trema_ph_push_sample_unlocked(float ph, uint16_t raw, uint8_t err, bool stable)
{
    if (s_sample_q == NULL) {
        return;
    }
    trema_ph_measurement_t m = {.ph = ph,
                                .raw_thousandths = raw,
                                .error_flags = err,
                                .stable = stable,
                                .valid = true,
                                .tick_stamp = xTaskGetTickCount()};
    (void)xQueueOverwrite(s_sample_q, &m);
}

#define TREMA_PH_I2C_IO_RETRIES 10

#define TREMA_PH_SAMPLE_ATTEMPTS           4
#define TREMA_PH_SAMPLE_ATTEMPTS_RECOVERY  3
#define TREMA_PH_SAMPLE_RETRY_DELAY_MS     120U
#define TREMA_PH_RECOVERY_POST_RESET_MS    100U
#define TREMA_PH_RAW_THOUSANDTHS_MAX       14000U

#define TREMA_PH_FW_STABILITY_SUPPORTED_MIN 6U
#define TREMA_PH_POST_INIT_RESET_DELAY_MS   50U

#ifndef TREMA_PH_ENABLE_SOFT_RESET
#define TREMA_PH_ENABLE_SOFT_RESET 0
#endif

static bool use_stub_values = false;
static float stub_ph = 6.5f;

static bool s_i2c_logs_suppressed = false;
static bool s_missing_reported = false;
static esp_err_t s_last_missing_err = ESP_OK;

static uint8_t data[4];

static bool sensor_initialized = false;

static bool s_last_read_stability_known;
static bool s_last_read_stable;
static uint8_t s_module_fw_version;
static bool s_wiki_measurement_hint_logged;

static void trema_ph_suppress_i2c_logs(void)
{
    if (s_i2c_logs_suppressed) {
        return;
    }
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
    uint8_t reg = TREMA_PH_REG_PH_ERROR;
    return i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg, 1, err_byte, 1, 1000);
}

static esp_err_t trema_ph_read_registers(uint8_t start_reg, uint8_t *out, size_t len)
{
    esp_err_t last_err = ESP_ERR_INVALID_RESPONSE;
    ESP_LOGD(TAG, "[I2C] read start: bus=1 addr=0x%02X reg=0x%02X len=%u", s_ph_i2c_addr_7bit, start_reg, (unsigned)len);
    for (int attempt = 0; attempt < TREMA_PH_I2C_IO_RETRIES; attempt++) {
        last_err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &start_reg, 1, out, len, 1000);
        if (last_err == ESP_OK) {
            esp_rom_delay_us(500);
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    ESP_LOGW(TAG, "[I2C] read FAIL bus=1 addr=0x%02X reg=0x%02X len=%u after %d tries: %s (0x%x)", s_ph_i2c_addr_7bit,
             start_reg, (unsigned)len, TREMA_PH_I2C_IO_RETRIES, esp_err_to_name(last_err), last_err);
    return last_err;
}

/** Как `iarduino_I2C_pH::_writeBytes`: до 10 попыток, затем delay(10). */
static esp_err_t trema_ph_write_registers(uint8_t start_reg, const uint8_t *src, size_t len)
{
    esp_err_t last_err = ESP_FAIL;
    for (int attempt = 0; attempt < TREMA_PH_I2C_IO_RETRIES; attempt++) {
        last_err = i2c_bus_write_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &start_reg, 1, src, len, 1000);
        if (last_err == ESP_OK) {
            /* Как iarduino `_writeBytes`: только delay(10), без delayMicroseconds после записи */
            vTaskDelay(pdMS_TO_TICKS(10));
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    ESP_LOGW(TAG, "[I2C] write FAIL addr=0x%02X reg=0x%02X len=%u: %s", s_ph_i2c_addr_7bit, start_reg, (unsigned)len,
             esp_err_to_name(last_err));
    return last_err;
}

static void trema_ph_invalidate_ph_read_cache(void)
{
    if (!i2c_cache_is_initialized()) {
        return;
    }
    uint8_t reg_ph = TREMA_PH_REG_PH_pH;
    (void)i2c_cache_invalidate(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1);
}

static bool trema_ph_soft_reset_hw(void)
{
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGW(TAG, "[soft reset] bus 1 not initialized");
        return false;
    }

    uint8_t reg_bits = TREMA_PH_REG_BITS_0;
    esp_err_t err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_bits, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "pH soft reset: read REG_BITS_0 failed: %s", esp_err_to_name(err));
        return false;
    }
    esp_rom_delay_us(500);

    uint8_t reset_value = data[0] | 0x80U;
    err = i2c_bus_write_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_bits, 1, &reset_value, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "pH soft reset: write REG_BITS_0 failed: %s", esp_err_to_name(err));
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(10));

    uint8_t reg_flags = TREMA_PH_REG_FLAGS_0;
    for (int poll = 0; poll < 100; poll++) {
        err = i2c_bus_read_bus(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_flags, 1, data, 1, 500);
        if (err == ESP_OK && (data[0] & 0x80U) != 0) {
            trema_ph_invalidate_ph_read_cache();
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }

    ESP_LOGW(TAG, "pH soft reset: timeout waiting for REG_FLAGS_0 completion bit");
    return false;
}

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
        ESP_LOGW(TAG, "pH header: chip id 0x%02X (expected Flash 0x%02X or Metro 0x%02X)", hdr[3], TREMA_PH_CHIP_ID_FLASH,
                 TREMA_PH_CHIP_ID_METRO);
        return false;
    }
    return true;
}

static esp_err_t trema_ph_probe_model_header_at_addr(uint8_t addr_7bit, uint8_t hdr[4])
{
    s_ph_i2c_addr_7bit = addr_7bit;
    esp_err_t e = trema_ph_read_registers(TREMA_PH_REG_MODEL, hdr, 4);
    if (e != ESP_OK) {
        return e;
    }
    if (!trema_ph_validate_module_header(hdr)) {
        return ESP_ERR_INVALID_RESPONSE;
    }
    return ESP_OK;
}

static bool trema_ph_addr_in_u8_list(uint8_t a, const uint8_t *list, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        if (list[i] == a) {
            return true;
        }
    }
    return false;
}

/**
 * Как iarduino `_begin`: сначала приоритетные адреса, затем как при «адрес 0» — поиск по шине.
 * Используем `i2c_bus_scan_bus` (0x08…0x77), затем добор по адресам, не попавшим в scan.
 */
static esp_err_t trema_ph_read_header_with_discovery(uint8_t hdr[4])
{
    const uint8_t preferred = s_ph_i2c_addr_7bit;
    uint8_t try_list[3];
    size_t n_try = 0;
    try_list[n_try++] = preferred;
    const uint8_t common[] = {0x09, 0x0A};
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
        last_err = trema_ph_probe_model_header_at_addr(try_a, hdr);
        if (last_err == ESP_OK) {
            if (try_a != preferred) {
                ESP_LOGI(TAG, "pH модуль отвечает по I²C 0x%02X (до поиска ожидали 0x%02X)", try_a, preferred);
            }
            return ESP_OK;
        }
    }

    uint8_t scan_buf[120];
    size_t scan_n = 0;
    if (i2c_bus_scan_bus(I2C_BUS_1, scan_buf, sizeof(scan_buf), &scan_n) == ESP_OK && scan_n > 0) {
        for (size_t si = 0; si < scan_n; si++) {
            uint8_t a = scan_buf[si];
            if (trema_ph_addr_in_u8_list(a, try_list, n_try)) {
                continue;
            }
            last_err = trema_ph_probe_model_header_at_addr(a, hdr);
            if (last_err == ESP_OK) {
                ESP_LOGI(TAG, "pH модуль найден сканированием шины @7-bit 0x%02X (ожидали 0x%02X)", a, preferred);
                return ESP_OK;
            }
        }
    }

    for (unsigned ai = 0x08; ai < 0x78; ai++) {
        uint8_t a = (uint8_t)ai;
        if (trema_ph_addr_in_u8_list(a, try_list, n_try)) {
            continue;
        }
        bool in_scan = false;
        for (size_t si = 0; si < scan_n; si++) {
            if (scan_buf[si] == a) {
                in_scan = true;
                break;
            }
        }
        if (in_scan) {
            continue;
        }
        last_err = trema_ph_probe_model_header_at_addr(a, hdr);
        if (last_err == ESP_OK) {
            ESP_LOGI(TAG, "pH модуль найден полным перебором 0x08…0x77 @7-bit 0x%02X", a);
            return ESP_OK;
        }
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
    TREMA_TRACE_INIT("read header REG_MODEL..CHIP_ID (discovery 0x%02X / 0x09|0x0A)", s_ph_i2c_addr_7bit);
    esp_err_t err = trema_ph_read_header_with_discovery(hdr);
    if (err != ESP_OK) {
        trema_ph_report_missing(err);
        TREMA_TRACE_INIT("abort: header I2C err=%s", esp_err_to_name(err));
        goto out;
    }
    TREMA_TRACE_INIT("header bytes: M=0x%02X V=0x%02X A=0x%02X C=0x%02X addr_7bit=0x%02X", hdr[0], hdr[1], hdr[2],
                     hdr[3], s_ph_i2c_addr_7bit);
    s_module_fw_version = hdr[1];
#if TREMA_PH_ENABLE_SOFT_RESET
    if (!trema_ph_soft_reset_hw()) {
        ESP_LOGW(TAG, "pH sensor soft reset after probe failed (continuing init like iarduino)");
    }
    vTaskDelay(pdMS_TO_TICKS(TREMA_PH_POST_INIT_RESET_DELAY_MS));
    TREMA_TRACE_INIT("post-reset delay %ums done", (unsigned)TREMA_PH_POST_INIT_RESET_DELAY_MS);
#else
    vTaskDelay(pdMS_TO_TICKS(5));
    TREMA_TRACE_INIT("post-probe 5ms (TREMA_PH_ENABLE_SOFT_RESET=0, без soft reset)");
#endif

    sensor_initialized = true;
    use_stub_values = false;
    s_missing_reported = false;
    s_last_missing_err = ESP_OK;
    ESP_LOGI(TAG, "pH sensor OK (fw=%u, chip=0x%02X)", (unsigned)hdr[1], hdr[3]);
    if (!s_wiki_measurement_hint_logged) {
        s_wiki_measurement_hint_logged = true;
        ESP_LOGI(TAG,
                 "pH измерения (wiki iarduino): полное погружение щупа; после погружения выдержка ≥1 мин до "
                 "замеров; гальваническая развязка I²C/питания при совместной работе с TDS/другими электродами");
    }
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
    s_last_read_stability_known = false;
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

    uint8_t reg_ph = TREMA_PH_REG_PH_pH;
    uint8_t ph_bytes[2];
    esp_err_t err = ESP_ERR_NOT_FOUND;
    uint16_t last_raw = 0;
    uint8_t last_err_flags = 0;
    bool had_transport_err = false;
    esp_err_t last_xfer_err = ESP_OK;
    bool had_sentinel = false;
    bool recovery_done = false;
    const int read_phases = TREMA_PH_ENABLE_SOFT_RESET ? 2 : 1;

    for (int phase = 0; phase < read_phases && !ok; phase++) {
        int max_try = TREMA_PH_SAMPLE_ATTEMPTS;
        if (phase == 1) {
            if (!had_sentinel && last_raw != 0xFFFFU) {
                break;
            }
            ESP_LOGI(TAG, "[pH read] recovery: soft reset после 0xFFFF, ещё %d попыток", TREMA_PH_SAMPLE_ATTEMPTS_RECOVERY);
            trema_ph_soft_reset_hw();
            vTaskDelay(pdMS_TO_TICKS(TREMA_PH_RECOVERY_POST_RESET_MS));
            trema_ph_invalidate_ph_read_cache();
            recovery_done = true;
            max_try = TREMA_PH_SAMPLE_ATTEMPTS_RECOVERY;
        }

        for (int sample_try = 0; sample_try < max_try; sample_try++) {
            if (sample_try > 0 || phase > 0) {
                trema_ph_invalidate_ph_read_cache();
                vTaskDelay(pdMS_TO_TICKS(TREMA_PH_SAMPLE_RETRY_DELAY_MS));
                TREMA_TRACE_READ("sample retry phase=%d %d/%d", phase, sample_try + 1, max_try);
            }

            err = ESP_ERR_NOT_FOUND;
            bool cache_allowed = (phase == 0 && sample_try == 0 && i2c_cache_is_initialized());
            bool from_cache_hit = false;

            if (cache_allowed) {
                err = i2c_cache_get(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1, ph_bytes, 2, 500);
                if (err == ESP_OK) {
                    from_cache_hit = true;
                    TREMA_TRACE_READ("cache HIT reg=0x%02X bytes %02X %02X", reg_ph, ph_bytes[0], ph_bytes[1]);
                }
            }

            if (err != ESP_OK) {
                err = trema_ph_read_registers(reg_ph, ph_bytes, 2);
                from_cache_hit = false;
                if (err != ESP_OK) {
                    had_transport_err = true;
                    last_xfer_err = err;
                    continue;
                }
                TREMA_TRACE_READ("I2C raw %02X %02X", ph_bytes[0], ph_bytes[1]);
            }

            if (from_cache_hit) {
                esp_rom_delay_us(500);
            }

            uint8_t err_byte = 0;
            esp_err_t e2 = trema_ph_read_error_byte(&err_byte);
            if (e2 != ESP_OK) {
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
                had_sentinel = true;
                continue;
            }
            if (raw_high || ph_val < 0.0f || ph_val > 14.0f) {
                (void)stab_bad;
                continue;
            }

            *ph = ph_val;
            if (s_module_fw_version >= TREMA_PH_FW_STABILITY_SUPPORTED_MIN) {
                s_last_read_stable = (err_byte & PH_FLG_STAB_ERR) == 0;
            } else {
                s_last_read_stable = true;
            }
            s_last_read_stability_known = true;
            if (i2c_cache_is_initialized() && !from_cache_hit) {
                i2c_cache_put(I2C_BUS_1, s_ph_i2c_addr_7bit, &reg_ph, 1, ph_bytes, 2, 500);
                TREMA_TRACE_READ("cache PUT после валидации (I2C)");
            }

            use_stub_values = false;
            s_missing_reported = false;
            s_last_missing_err = ESP_OK;
            TREMA_TRACE_READ("SUCCESS pH=%.4f", (double)*ph);

            trema_ph_push_sample_unlocked(*ph, pH_raw, err_byte, s_last_read_stable);

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
    }

    trema_ph_invalidate_ph_read_cache();
    ESP_LOGW(TAG,
             "[pH read] FAIL после всех попыток%s: последний raw=0x%04X REG_PH_ERROR=0x%02X",
             recovery_done ? " (+recovery)" : "", (unsigned)last_raw, last_err_flags);
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

static uint8_t trema_ph_get_calibration_status_locked(void)
{
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        return 0;
    }
    uint8_t reg_cal = TREMA_PH_REG_PH_CALIBRATION;
    if (trema_ph_read_registers(reg_cal, data, 1) != ESP_OK) {
        return 0;
    }
    if (data[0] & PH_FLG_STATUS_1) {
        return 1;
    }
    if (data[0] & PH_FLG_STATUS_2) {
        return 2;
    }
    return 0;
}

bool trema_ph_calibrate(uint8_t stage, float known_pH)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        goto out;
    }

    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGE(TAG, "I²C bus 1 not initialized");
        goto out;
    }

    if ((stage != 1 && stage != 2) || known_pH < 0.0f || known_pH > 14.0f) {
        ESP_LOGW(TAG, "Invalid calibration parameters");
        goto out;
    }

    uint8_t reg_known_ph = TREMA_PH_REG_PH_KNOWN_PH;
    uint16_t ph_value_int = (uint16_t)(known_pH * 1000.0f);
    uint8_t ph_data[2] = {(uint8_t)(ph_value_int & 0xFFU), (uint8_t)((ph_value_int >> 8) & 0xFFU)};

    if (trema_ph_write_registers(reg_known_ph, ph_data, 2) != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write known pH value");
        goto out;
    }

    uint8_t reg_cal = TREMA_PH_REG_PH_CALIBRATION;
    uint8_t cal_cmd = (uint8_t)((stage == 1 ? PH_BIT_CALC_1 : PH_BIT_CALC_2) | PH_CODE_CALC_SAVE);

    if (trema_ph_write_registers(reg_cal, &cal_cmd, 1) != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send calibration command");
        goto out;
    }

    ESP_LOGI(TAG, "Calibration stage %d started with pH %.3f", stage, known_pH);

    const uint32_t poll_ms = 200U;
    const uint32_t idle_giveup_ms = 5000U;
    const uint32_t max_busy_wait_ms = 45000U;
    uint32_t elapsed = 0U;
    bool saw_non_idle = false;

    while (elapsed < max_busy_wait_ms) {
        uint8_t st = trema_ph_get_calibration_status_locked();
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

    if (saw_non_idle && trema_ph_get_calibration_status_locked() != 0) {
        ESP_LOGW(TAG, "pH cal: timeout waiting for idle after busy (stage %u)", (unsigned)stage);
        ok = false;
        goto out;
    }
    if (!saw_non_idle) {
        ESP_LOGW(TAG, "pH cal: module did not report busy flags (older firmware?); settling 2 s before result check");
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    uint8_t reg_error = TREMA_PH_REG_PH_ERROR;
    if (trema_ph_read_registers(reg_error, data, 1) != ESP_OK) {
        ok = false;
        goto out;
    }
    ok = (data[0] & PH_FLG_CALC_ERR) == 0;
    if (!ok) {
        ESP_LOGW(TAG, "pH cal: module CALC_ERR (stage %u) REG_PH_ERROR=0x%02X", (unsigned)stage, (unsigned)data[0]);
    }
out:
    trema_ph_invalidate_ph_read_cache();
    trema_ph_mutex_give();
    return ok;
}

uint8_t trema_ph_get_calibration_status(void)
{
    trema_ph_mutex_take();
    uint8_t ret = trema_ph_get_calibration_status_locked();
    trema_ph_mutex_give();
    return ret;
}

bool trema_ph_get_calibration_result(void)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    uint8_t reg_error = TREMA_PH_REG_PH_ERROR;
    if (trema_ph_read_registers(reg_error, data, 1) != ESP_OK) {
        goto out;
    }
    ok = (data[0] & PH_FLG_CALC_ERR) == 0;
    if (!ok) {
        ESP_LOGW(TAG, "REG_PH_ERROR=0x%02X after cal attempt: CALC_ERR%s", (unsigned)data[0],
                 (data[0] & PH_FLG_STAB_ERR) ? ", STAB_ERR" : "");
    }
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_get_stability(void)
{
    trema_ph_mutex_take();
    bool ok_st = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }

    if (s_module_fw_version > 0 && s_module_fw_version < TREMA_PH_FW_STABILITY_SUPPORTED_MIN) {
        ok_st = true;
        goto out;
    }

    uint8_t reg_error = TREMA_PH_REG_PH_ERROR;
    if (trema_ph_read_registers(reg_error, data, 1) != ESP_OK) {
        goto out;
    }
    ok_st = (data[0] & PH_FLG_STAB_ERR) == 0;
out:
    trema_ph_mutex_give();
    return ok_st;
}

bool trema_ph_get_last_read_stability(void)
{
    trema_ph_mutex_take();
    bool out = s_last_read_stability_known && s_last_read_stable;
    trema_ph_mutex_give();
    return out;
}

uint8_t trema_ph_get_firmware_version(void)
{
    return s_module_fw_version;
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
    /* Как iarduino reset(): переинициализация мастера после отпускания подтяжек модулем */
    (void)i2c_bus_reset_bus(I2C_BUS_1);
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
        ESP_LOGW(TAG, "I²C bus 1 -> pH модуль: нет ответа (базовый addr 0x%02X): %s", s_ph_i2c_addr_7bit,
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
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    trema_ph_suppress_i2c_logs();
    uint8_t hdr[4];
    esp_err_t e = trema_ph_read_header_with_discovery(hdr);
    if (e != ESP_OK) {
        goto out;
    }
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

/* ========== Порт остальных методов iarduino_I2C_pH ========== */

bool trema_ph_change_i2c_address(uint8_t new_addr_7bit)
{
    if (new_addr_7bit > 0x7FU) {
        new_addr_7bit >>= 1;
    }
    /* Как iarduino changeAddress: запрещены только 0x00 и 0x7F (не сужаем до 0x08…0x77). */
    if (new_addr_7bit == 0x00U || new_addr_7bit == 0x7FU) {
        ESP_LOGW(TAG, "change_i2c_address: invalid new addr 0x%02X (forbidden 0x00/0x7F)", new_addr_7bit);
        return false;
    }

    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }

    uint8_t reg_bits = TREMA_PH_REG_BITS_0;
    if (trema_ph_read_registers(reg_bits, data, 1) != ESP_OK) {
        goto out;
    }
    data[0] = (uint8_t)((data[0] & (uint8_t)~TREMA_PH_BIT_BLOCK_ADR) | TREMA_PH_BIT_SAVE_ADR_EN);
    if (trema_ph_write_registers(reg_bits, data, 1) != ESP_OK) {
        goto out;
    }

    uint8_t addr_byte = (uint8_t)((new_addr_7bit << 1) | 1U);
    uint8_t reg_addr = TREMA_PH_REG_ADDRESS;
    if (trema_ph_write_registers(reg_addr, &addr_byte, 1) != ESP_OK) {
        goto out;
    }

    vTaskDelay(pdMS_TO_TICKS(200));

    uint8_t prev = s_ph_i2c_addr_7bit;
    s_ph_i2c_addr_7bit = new_addr_7bit;
    uint8_t hdr[4];
    if (trema_ph_read_registers(TREMA_PH_REG_MODEL, hdr, 4) != ESP_OK || !trema_ph_validate_module_header(hdr)) {
        s_ph_i2c_addr_7bit = prev;
        goto out;
    }

    ESP_LOGI(TAG, "pH module I²C address changed to 0x%02X", new_addr_7bit);
    trema_ph_invalidate_ph_read_cache();
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_get_pull_i2c(bool *pull_enabled_out)
{
    if (pull_enabled_out == NULL) {
        return false;
    }
    *pull_enabled_out = false;
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    uint8_t r = TREMA_PH_REG_FLAGS_0;
    if (trema_ph_read_registers(r, data, 2) != ESP_OK) {
        goto out;
    }
    /* Как iarduino getPullI2C: true только если поддержка есть И подтяжка включена (бит SET_I2C_UP). */
    if ((data[0] & TREMA_PH_FLG_I2C_UP) == 0) {
        goto out;
    }
    if ((data[1] & TREMA_PH_BIT_I2C_UP) == 0) {
        goto out;
    }
    *pull_enabled_out = true;
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

bool trema_ph_set_pull_i2c(bool enable)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    uint8_t r = TREMA_PH_REG_FLAGS_0;
    if (trema_ph_read_registers(r, data, 2) != ESP_OK) {
        goto out;
    }
    if ((data[0] & TREMA_PH_FLG_I2C_UP) == 0) {
        ESP_LOGW(TAG, "set_pull_i2c: module does not support I²C pull control (FLG_I2C_UP clear)");
        goto out;
    }
    uint8_t bits0 = enable ? (uint8_t)(data[1] | TREMA_PH_BIT_I2C_UP) : (uint8_t)(data[1] & (uint8_t)~TREMA_PH_BIT_I2C_UP);
    uint8_t regw = TREMA_PH_REG_BITS_0;
    if (trema_ph_write_registers(regw, &bits0, 1) != ESP_OK) {
        goto out;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

float trema_ph_get_known_ph(uint8_t stage)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1) || stage < 1 || stage > 2) {
        goto out;
    }
    uint8_t reg = (stage == 1) ? TREMA_PH_REG_PH_KNOWN_PH_1 : TREMA_PH_REG_PH_KNOWN_PH_2;
    if (trema_ph_read_registers(reg, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.001f;
out:
    trema_ph_mutex_give();
    return v;
}

bool trema_ph_set_known_ph(uint8_t stage, float known_ph)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1) || stage < 1 || stage > 2 || known_ph < 0.0f ||
        known_ph > 14.0f) {
        goto out;
    }
    uint8_t unlock = PH_CODE_CALC_SAVE;
    if (trema_ph_write_registers(TREMA_PH_REG_PH_CALIBRATION, &unlock, 1) != ESP_OK) {
        goto out;
    }
    uint16_t w = (uint16_t)(known_ph * 1000.0f);
    data[0] = (uint8_t)(w & 0xFFU);
    data[1] = (uint8_t)((w >> 8) & 0xFFU);
    uint8_t reg = (stage == 1) ? TREMA_PH_REG_PH_KNOWN_PH_1 : TREMA_PH_REG_PH_KNOWN_PH_2;
    if (trema_ph_write_registers(reg, data, 2) != ESP_OK) {
        goto out;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

float trema_ph_get_ky(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_Ky, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.001f;
out:
    trema_ph_mutex_give();
    return v;
}

bool trema_ph_set_ky(float ky)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1) || ky < 1.0f || ky > 65.535f) {
        goto out;
    }
    uint8_t unlock = PH_CODE_CALC_SAVE;
    if (trema_ph_write_registers(TREMA_PH_REG_PH_CALIBRATION, &unlock, 1) != ESP_OK) {
        goto out;
    }
    uint16_t w = (uint16_t)(ky * 1000.0f);
    data[0] = (uint8_t)(w & 0xFFU);
    data[1] = (uint8_t)((w >> 8) & 0xFFU);
    if (trema_ph_write_registers(TREMA_PH_REG_PH_Ky, data, 2) != ESP_OK) {
        goto out;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

float trema_ph_get_vstp(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_Ustp, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.01f;
out:
    trema_ph_mutex_give();
    return v;
}

bool trema_ph_set_vstp(float vstp_mv)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1) || vstp_mv < 0.01f || vstp_mv > 655.35f) {
        goto out;
    }
    uint8_t unlock = PH_CODE_CALC_SAVE;
    if (trema_ph_write_registers(TREMA_PH_REG_PH_CALIBRATION, &unlock, 1) != ESP_OK) {
        goto out;
    }
    uint16_t w = (uint16_t)(vstp_mv * 100.0f);
    data[0] = (uint8_t)(w & 0xFFU);
    data[1] = (uint8_t)((w >> 8) & 0xFFU);
    if (trema_ph_write_registers(TREMA_PH_REG_PH_Ustp, data, 2) != ESP_OK) {
        goto out;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}

float trema_ph_get_u_in(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_Uin, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.0001f;
out:
    trema_ph_mutex_give();
    return v;
}

float trema_ph_get_u_out(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_Uout, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.0001f;
out:
    trema_ph_mutex_give();
    return v;
}

float trema_ph_get_u_n(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_Un, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.0001f;
out:
    trema_ph_mutex_give();
    return v;
}

float trema_ph_get_phn(void)
{
    trema_ph_mutex_take();
    float v = 0.0f;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        goto out;
    }
    if (trema_ph_read_registers(TREMA_PH_REG_PH_pHn, data, 2) != ESP_OK) {
        goto out;
    }
    uint16_t raw = (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
    v = (float)raw * 0.001f;
out:
    trema_ph_mutex_give();
    return v;
}

bool trema_ph_set_phn(float phn)
{
    trema_ph_mutex_take();
    bool ok = false;
    if (!sensor_initialized || !i2c_bus_is_initialized_bus(I2C_BUS_1) || phn < 0.0f || phn > 14.0f) {
        goto out;
    }
    uint8_t unlock = PH_CODE_CALC_SAVE;
    if (trema_ph_write_registers(TREMA_PH_REG_PH_CALIBRATION, &unlock, 1) != ESP_OK) {
        goto out;
    }
    uint16_t w = (uint16_t)(phn * 1000.0f);
    data[0] = (uint8_t)(w & 0xFFU);
    data[1] = (uint8_t)((w >> 8) & 0xFFU);
    if (trema_ph_write_registers(TREMA_PH_REG_PH_pHn, data, 2) != ESP_OK) {
        goto out;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    ok = true;
out:
    trema_ph_mutex_give();
    return ok;
}
