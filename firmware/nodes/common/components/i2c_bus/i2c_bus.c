/**
 * @file i2c_bus.c
 * @brief Реализация общего драйвера I²C шины (ESP-IDF i2c_master v2)
 */

#include "i2c_bus.h"
#include "esp_log.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <limits.h>
#include <stdint.h>
#include <string.h>

static const char *TAG = "i2c_bus";

static int i2c_bus_master_timeout_ms(uint32_t timeout_ms)
{
    if (timeout_ms > (uint32_t)INT_MAX) {
        return INT_MAX;
    }
    return (int)timeout_ms;
}

#define I2C_BUS_DEV_CACHE_SLOTS 8

typedef struct {
    bool used;
    uint8_t device_address;
    i2c_master_dev_handle_t handle;
} i2c_bus_dev_slot_t;

typedef struct {
    i2c_master_bus_handle_t bus_handle;
    i2c_bus_config_t config;
    bool initialized;
    SemaphoreHandle_t mutex;
    i2c_bus_dev_slot_t dev_slots[I2C_BUS_DEV_CACHE_SLOTS];
} i2c_bus_state_t;

static i2c_bus_state_t s_buses[I2C_BUS_MAX] = {0};

/** Индекс слота для вытеснения при полном кэше dev-handle (round-robin по шине). */
static uint8_t s_dev_evict_cursor[I2C_BUS_MAX];

#define I2C_BUS_DEFAULT_SDA_PIN 21
#define I2C_BUS_DEFAULT_SCL_PIN 22
#define I2C_BUS_DEFAULT_CLOCK_SPEED 100000

static esp_err_t i2c_bus_deinit_bus(i2c_bus_id_t bus_id);
static esp_err_t i2c_bus_recover_bus(i2c_bus_id_t bus_id);

void i2c_bus_xfer_opts_default(uint32_t xfer_timeout_ms, i2c_bus_xfer_opts_t *out)
{
    if (out == NULL) {
        return;
    }
    out->xfer_timeout_ms = xfer_timeout_ms;
    out->lock_timeout_ms = 0;
    out->read_extra_retries = 0;
}

static uint32_t i2c_bus_resolve_lock_timeout_ms(uint32_t xfer_ms, uint32_t lock_ms)
{
    if (lock_ms != 0) {
        return lock_ms;
    }
    uint64_t sum = (uint64_t)xfer_ms + (uint64_t)I2C_BUS_LOCK_MARGIN_MS;
    if (sum < (uint64_t)I2C_BUS_MIN_LOCK_TIMEOUT_MS) {
        return I2C_BUS_MIN_LOCK_TIMEOUT_MS;
    }
    if (sum > (uint64_t)UINT32_MAX) {
        return UINT32_MAX;
    }
    return (uint32_t)sum;
}

static bool i2c_bus_err_is_transient(esp_err_t e)
{
    return (e == ESP_ERR_TIMEOUT || e == ESP_FAIL || e == ESP_ERR_INVALID_STATE || e == ESP_ERR_INVALID_RESPONSE ||
            e == ESP_ERR_INVALID_CRC);
}

static void i2c_bus_dev_cache_clear_all(i2c_bus_state_t *bus)
{
    if (bus == NULL) {
        return;
    }
    for (size_t i = 0; i < I2C_BUS_DEV_CACHE_SLOTS; i++) {
        if (bus->dev_slots[i].used && bus->dev_slots[i].handle != NULL && bus->bus_handle != NULL) {
            (void)i2c_master_bus_rm_device(bus->dev_slots[i].handle);
        }
        bus->dev_slots[i].used = false;
        bus->dev_slots[i].handle = NULL;
        bus->dev_slots[i].device_address = 0;
    }
}

static esp_err_t i2c_bus_dev_cache_remove_addr(i2c_bus_state_t *bus, uint8_t addr_7bit)
{
    for (size_t i = 0; i < I2C_BUS_DEV_CACHE_SLOTS; i++) {
        if (bus->dev_slots[i].used && bus->dev_slots[i].device_address == addr_7bit) {
            if (bus->bus_handle != NULL && bus->dev_slots[i].handle != NULL) {
                (void)i2c_master_bus_rm_device(bus->dev_slots[i].handle);
            }
            bus->dev_slots[i].used = false;
            bus->dev_slots[i].handle = NULL;
            bus->dev_slots[i].device_address = 0;
            return ESP_OK;
        }
    }
    return ESP_ERR_NOT_FOUND;
}

static esp_err_t i2c_bus_dev_get_or_create(i2c_bus_state_t *bus, uint8_t addr_7bit, i2c_master_dev_handle_t *out)
{
    for (size_t i = 0; i < I2C_BUS_DEV_CACHE_SLOTS; i++) {
        if (bus->dev_slots[i].used && bus->dev_slots[i].device_address == addr_7bit) {
            *out = bus->dev_slots[i].handle;
            return ESP_OK;
        }
    }

    size_t slot = (size_t)-1;
    for (size_t i = 0; i < I2C_BUS_DEV_CACHE_SLOTS; i++) {
        if (!bus->dev_slots[i].used) {
            slot = i;
            break;
        }
    }
    if (slot == (size_t)-1) {
        const size_t bid = (size_t)(bus - s_buses);
        if (bid < I2C_BUS_MAX) {
            slot = (size_t)(s_dev_evict_cursor[bid] % (uint8_t)I2C_BUS_DEV_CACHE_SLOTS);
            s_dev_evict_cursor[bid]++;
        } else {
            slot = 0;
        }
        if (bus->dev_slots[slot].used && bus->dev_slots[slot].handle != NULL && bus->bus_handle != NULL) {
            (void)i2c_master_bus_rm_device(bus->dev_slots[slot].handle);
        }
        bus->dev_slots[slot].used = false;
        bus->dev_slots[slot].handle = NULL;
        bus->dev_slots[slot].device_address = 0;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr_7bit,
        .scl_speed_hz = bus->config.clock_speed,
    };
    i2c_master_dev_handle_t h = NULL;
    esp_err_t e = i2c_master_bus_add_device(bus->bus_handle, &dev_cfg, &h);
    if (e != ESP_OK) {
        return e;
    }
    bus->dev_slots[slot].used = true;
    bus->dev_slots[slot].device_address = addr_7bit;
    bus->dev_slots[slot].handle = h;
    *out = h;
    return ESP_OK;
}

static esp_err_t i2c_bus_one_read(i2c_master_dev_handle_t dev_handle, const uint8_t *reg_addr, size_t reg_addr_len,
                                  uint8_t *data, size_t data_len, uint32_t xfer_ms)
{
    const int tmo = i2c_bus_master_timeout_ms(xfer_ms);
    if (reg_addr != NULL && reg_addr_len > 0) {
        return i2c_master_transmit_receive(dev_handle, reg_addr, reg_addr_len, data, data_len, tmo);
    }
    return i2c_master_receive(dev_handle, data, data_len, tmo);
}

esp_err_t i2c_bus_forget_device(i2c_bus_id_t bus_id, uint8_t device_addr_7bit)
{
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    i2c_bus_state_t *bus = &s_buses[bus_id];
    if (!bus->initialized || bus->mutex == NULL || bus->bus_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t rm = i2c_bus_dev_cache_remove_addr(bus, device_addr_7bit);
    xSemaphoreGive(bus->mutex);
    return (rm == ESP_ERR_NOT_FOUND) ? ESP_ERR_NOT_FOUND : ESP_OK;
}

esp_err_t i2c_bus_init(const i2c_bus_config_t *config)
{
    return i2c_bus_init_bus(I2C_BUS_0, config);
}

esp_err_t i2c_bus_init_bus(i2c_bus_id_t bus_id, const i2c_bus_config_t *config)
{
    ESP_LOGI(TAG, "=== I²C Bus %d Init Start ===", bus_id);

    if (bus_id >= I2C_BUS_MAX) {
        ESP_LOGE(TAG, "Invalid bus_id: %d", bus_id);
        return ESP_ERR_INVALID_ARG;
    }

    if (config == NULL) {
        ESP_LOGE(TAG, "Invalid config: NULL");
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    ESP_LOGI(TAG, "I²C bus %d config: SDA=%d, SCL=%d, speed=%d Hz, pullup=%s",
             bus_id, config->sda_pin, config->scl_pin, config->clock_speed,
             config->pullup_enable ? "enabled" : "disabled");

    if (bus->initialized) {
        ESP_LOGW(TAG, "I²C bus %d already initialized", bus_id);
        return ESP_OK;
    }

    if (bus->mutex == NULL) {
        bus->mutex = xSemaphoreCreateMutex();
        if (bus->mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create mutex for bus %d", bus_id);
            return ESP_ERR_NO_MEM;
        }
    }

    memcpy(&bus->config, config, sizeof(i2c_bus_config_t));
    memset(bus->dev_slots, 0, sizeof(bus->dev_slots));

    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = (i2c_port_t)bus_id,
        .sda_io_num = config->sda_pin,
        .scl_io_num = config->scl_pin,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags = {
            .enable_internal_pullup = config->pullup_enable
        }
    };

    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus->bus_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I²C master bus %d: %s", bus_id, esp_err_to_name(err));
        vSemaphoreDelete(bus->mutex);
        bus->mutex = NULL;
        return err;
    }

    bus->initialized = true;
    ESP_LOGI(TAG, "I²C bus %d initialized successfully", bus_id);
    return ESP_OK;
}

esp_err_t i2c_bus_deinit(void)
{
    return i2c_bus_deinit_bus(I2C_BUS_0);
}

static esp_err_t i2c_bus_deinit_bus(i2c_bus_id_t bus_id)
{
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized) {
        return ESP_OK;
    }

    if (bus->bus_handle != NULL) {
        i2c_bus_dev_cache_clear_all(bus);
        esp_err_t err = i2c_del_master_bus(bus->bus_handle);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to delete I²C master bus %d: %s", bus_id, esp_err_to_name(err));
        }
        bus->bus_handle = NULL;
    }

    if (bus->mutex != NULL) {
        vSemaphoreDelete(bus->mutex);
        bus->mutex = NULL;
    }

    bus->initialized = false;
    memset(&bus->config, 0, sizeof(i2c_bus_config_t));
    memset(bus->dev_slots, 0, sizeof(bus->dev_slots));
    if (bus_id < I2C_BUS_MAX) {
        s_dev_evict_cursor[bus_id] = 0;
    }

    ESP_LOGI(TAG, "I²C bus %d deinitialized", bus_id);
    return ESP_OK;
}

bool i2c_bus_is_initialized(void)
{
    return i2c_bus_is_initialized_bus(I2C_BUS_0);
}

bool i2c_bus_is_initialized_bus(i2c_bus_id_t bus_id)
{
    if (bus_id >= I2C_BUS_MAX) {
        return false;
    }
    return s_buses[bus_id].initialized;
}

esp_err_t i2c_bus_read(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                       uint8_t *data, size_t data_len, uint32_t timeout_ms)
{
    return i2c_bus_read_bus(I2C_BUS_0, device_addr, reg_addr, reg_addr_len, data, data_len, timeout_ms);
}

esp_err_t i2c_bus_read_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                           uint8_t *data, size_t data_len, uint32_t timeout_ms)
{
    i2c_bus_xfer_opts_t o;
    i2c_bus_xfer_opts_default(timeout_ms, &o);
    return i2c_bus_read_bus_ex(bus_id, device_addr, reg_addr, reg_addr_len, data, data_len, &o);
}

esp_err_t i2c_bus_read_bus_ex(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                              uint8_t *data, size_t data_len, const i2c_bus_xfer_opts_t *opts)
{
    if (opts == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (bus_id >= I2C_BUS_MAX) {
        ESP_LOGE(TAG, "Invalid bus_id: %d", bus_id);
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized || bus->mutex == NULL || bus->bus_handle == NULL) {
        ESP_LOGE(TAG, "I²C bus %d not ready", bus_id);
        return ESP_ERR_INVALID_STATE;
    }

    if (data == NULL || data_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t extra = opts->read_extra_retries;
    if (extra > (uint8_t)(I2C_BUS_MAX_READ_ATTEMPTS - 1)) {
        extra = (uint8_t)(I2C_BUS_MAX_READ_ATTEMPTS - 1);
    }
    const int total_attempts = 1 + (int)extra;

    const uint32_t lock_ms = i2c_bus_resolve_lock_timeout_ms(opts->xfer_timeout_ms, opts->lock_timeout_ms);

    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(lock_ms)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for bus %d (read)", bus_id);
        return ESP_ERR_TIMEOUT;
    }

    esp_err_t err = ESP_OK;
    i2c_master_dev_handle_t dev = NULL;

    for (int attempt = 0; attempt < total_attempts; attempt++) {
        err = i2c_bus_dev_get_or_create(bus, device_addr, &dev);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "add_device bus %d addr 0x%02X: %s", bus_id, device_addr, esp_err_to_name(err));
            break;
        }

        err = i2c_bus_one_read(dev, reg_addr, reg_addr_len, data, data_len, opts->xfer_timeout_ms);
        if (err == ESP_OK) {
            break;
        }
        ESP_LOGD(TAG, "I²C read bus %d addr=0x%02X attempt %d/%d: %s", bus_id, device_addr, attempt + 1,
                 total_attempts, esp_err_to_name(err));

        if (!i2c_bus_err_is_transient(err)) {
            break;
        }

        if (attempt + 1 >= total_attempts) {
            break;
        }

        (void)i2c_bus_dev_cache_remove_addr(bus, device_addr);
        esp_err_t re = i2c_master_bus_reset(bus->bus_handle);
        if (re != ESP_OK) {
            ESP_LOGD(TAG, "i2c_master_bus_reset(bus %d) before read retry: %s", bus_id, esp_err_to_name(re));
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }

    xSemaphoreGive(bus->mutex);

    if (err != ESP_OK) {
        ESP_LOGD(TAG, "I²C read failed on bus %d: %s (addr=0x%02X)", bus_id, esp_err_to_name(err), device_addr);
    }

    return err;
}

esp_err_t i2c_bus_write(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                        const uint8_t *data, size_t data_len, uint32_t timeout_ms)
{
    return i2c_bus_write_bus(I2C_BUS_0, device_addr, reg_addr, reg_addr_len, data, data_len, timeout_ms);
}

esp_err_t i2c_bus_write_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                            const uint8_t *data, size_t data_len, uint32_t timeout_ms)
{
    i2c_bus_xfer_opts_t o;
    i2c_bus_xfer_opts_default(timeout_ms, &o);
    return i2c_bus_write_bus_ex(bus_id, device_addr, reg_addr, reg_addr_len, data, data_len, &o);
}

esp_err_t i2c_bus_write_bus_ex(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                               const uint8_t *data, size_t data_len, const i2c_bus_xfer_opts_t *opts)
{
    if (opts == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized || bus->mutex == NULL || bus->bus_handle == NULL) {
        ESP_LOGE(TAG, "I²C bus %d not ready (write)", bus_id);
        return ESP_ERR_INVALID_STATE;
    }

    if (data == NULL || data_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    const size_t reg_len = (reg_addr != NULL) ? reg_addr_len : 0;
    const size_t total_len = reg_len + data_len;
    if (total_len > I2C_BUS_MAX_COMBINED_WRITE) {
        ESP_LOGE(TAG, "I²C write combined len %zu > max %d", total_len, I2C_BUS_MAX_COMBINED_WRITE);
        return ESP_ERR_INVALID_ARG;
    }

    const uint32_t lock_ms = i2c_bus_resolve_lock_timeout_ms(opts->xfer_timeout_ms, opts->lock_timeout_ms);

    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(lock_ms)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for bus %d (write)", bus_id);
        return ESP_ERR_TIMEOUT;
    }

    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_bus_dev_get_or_create(bus, device_addr, &dev);
    if (err != ESP_OK) {
        xSemaphoreGive(bus->mutex);
        return err;
    }

    uint8_t write_buf[I2C_BUS_MAX_COMBINED_WRITE];
    if (reg_addr != NULL && reg_len > 0) {
        memcpy(write_buf, reg_addr, reg_len);
    }
    memcpy(write_buf + reg_len, data, data_len);

    err = i2c_master_transmit(dev, write_buf, total_len, i2c_bus_master_timeout_ms(opts->xfer_timeout_ms));

    xSemaphoreGive(bus->mutex);

    if (err != ESP_OK) {
        ESP_LOGD(TAG, "I²C write failed on bus %d: %s (addr=0x%02X)", bus_id, esp_err_to_name(err), device_addr);
    }

    return err;
}

esp_err_t i2c_bus_read_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t *data, uint32_t timeout_ms)
{
    return i2c_bus_read(device_addr, &reg_addr, 1, data, 1, timeout_ms);
}

esp_err_t i2c_bus_write_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t data, uint32_t timeout_ms)
{
    return i2c_bus_write(device_addr, &reg_addr, 1, &data, 1, timeout_ms);
}

esp_err_t i2c_bus_scan(uint8_t *found_addresses, size_t max_addresses, size_t *found_count)
{
    return i2c_bus_scan_bus(I2C_BUS_0, found_addresses, max_addresses, found_count);
}

esp_err_t i2c_bus_scan_bus(i2c_bus_id_t bus_id, uint8_t *found_addresses, size_t max_addresses, size_t *found_count)
{
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized || bus->mutex == NULL || bus->bus_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (found_addresses == NULL || found_count == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *found_count = 0;

    const uint32_t lock_ms = i2c_bus_resolve_lock_timeout_ms(5000, 5000);
    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(lock_ms)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    for (uint8_t addr = 0x08; addr < 0x78 && *found_count < max_addresses; addr++) {
        i2c_master_dev_handle_t dev_handle = NULL;
        i2c_device_config_t dev_cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = addr,
            .scl_speed_hz = bus->config.clock_speed,
        };

        esp_err_t aerr = i2c_master_bus_add_device(bus->bus_handle, &dev_cfg, &dev_handle);
        if (aerr == ESP_OK) {
            uint8_t dummy = 0;
            esp_err_t rerr = i2c_master_receive(dev_handle, &dummy, 1, i2c_bus_master_timeout_ms(35));
            if (rerr == ESP_OK) {
                found_addresses[*found_count] = addr;
                (*found_count)++;
            }
            (void)i2c_master_bus_rm_device(dev_handle);
        }
    }

    xSemaphoreGive(bus->mutex);
    return ESP_OK;
}

esp_err_t i2c_bus_recover(void)
{
    return i2c_bus_recover_bus(I2C_BUS_0);
}

esp_err_t i2c_bus_reset_bus(i2c_bus_id_t bus_id)
{
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized || bus->bus_handle == NULL || bus->mutex == NULL) {
        ESP_LOGW(TAG, "i2c_bus_reset_bus(%d): bus not ready", bus_id);
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
        ESP_LOGW(TAG, "i2c_bus_reset_bus(%d): mutex timeout", bus_id);
        return ESP_ERR_TIMEOUT;
    }

    esp_err_t err = i2c_master_bus_reset(bus->bus_handle);
    if (err == ESP_OK) {
        i2c_bus_dev_cache_clear_all(bus);
    }
    xSemaphoreGive(bus->mutex);

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "i2c_master_bus_reset(bus %d): %s", bus_id, esp_err_to_name(err));
    }

    return err;
}

static esp_err_t i2c_bus_recover_bus(i2c_bus_id_t bus_id)
{
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }

    i2c_bus_state_t *bus = &s_buses[bus_id];

    if (!bus->initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Recovering I²C bus %d...", bus_id);

    i2c_bus_config_t saved_config;
    memcpy(&saved_config, &bus->config, sizeof(i2c_bus_config_t));

    i2c_bus_deinit_bus(bus_id);
    vTaskDelay(pdMS_TO_TICKS(100));

    esp_err_t err = i2c_bus_init_bus(bus_id, &saved_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to reinitialize I²C bus %d after recovery", bus_id);
        return err;
    }

    ESP_LOGI(TAG, "I²C bus %d recovered successfully", bus_id);
    return ESP_OK;
}

esp_err_t i2c_bus_init_from_config(void)
{
    /*
     * I²C пины и скорость не входят в NodeConfig: задаются прошивкой (*_defaults.h / init_steps).
     * Функция сохранена для совместимости API — инициализирует только шину 0 дефолтами компонента.
     * Шина 1 — только через i2c_bus_init_bus(I2C_BUS_1, …) из кода ноды.
     */
    i2c_bus_config_t def = {
        .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
        .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
        .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
        .pullup_enable = false
    };
    ESP_LOGI(TAG, "i2c_bus_init_from_config: bus0 defaults SDA=%d SCL=%d speed=%lu Hz (internal, not NodeConfig)",
             def.sda_pin, def.scl_pin, (unsigned long)def.clock_speed);
    return i2c_bus_init(&def);
}
