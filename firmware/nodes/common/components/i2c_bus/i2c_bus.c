/**
 * @file i2c_bus.c
 * @brief Реализация общего драйвера I²C шины
 * 
 * Компонент реализует thread-safe доступ к I²C шине с поддержкой:
 * - Mutex для защиты от одновременного доступа
 * - Retry логика при ошибках
 * - I²C recovery при критических ошибках
 * - Интеграция с NodeConfig
 * 
 * Стандарты кодирования:
 * - Именование функций: i2c_bus_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t, логируют ошибки
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "i2c_bus.h"
#include "config_storage.h"
#include "esp_log.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include "cJSON.h"

static const char *TAG = "i2c_bus";

// Структура для хранения состояния шины
typedef struct {
    i2c_master_bus_handle_t bus_handle;
    i2c_bus_config_t config;
    bool initialized;
    SemaphoreHandle_t mutex;
} i2c_bus_state_t;

// Массив состояний для двух шин
static i2c_bus_state_t s_buses[I2C_BUS_MAX] = {0};

// Для обратной совместимости - указатель на шину 0
#define I2C_BUS_0_PTR (&s_buses[I2C_BUS_0])

// Константы
#define I2C_BUS_DEFAULT_TIMEOUT_MS 1000
#define I2C_BUS_MAX_RETRY_COUNT 3
#define I2C_BUS_DEFAULT_SDA_PIN 21  // ESP32 стандартный SDA
#define I2C_BUS_DEFAULT_SCL_PIN 22  // ESP32 стандартный SCL
#define I2C_BUS_DEFAULT_CLOCK_SPEED 100000

/**
 * @brief Внутренняя функция для выполнения I²C операции с retry
 */
static esp_err_t i2c_bus_operation_with_retry(esp_err_t (*operation)(void), const char *op_name) {
    esp_err_t err = ESP_OK;
    
    for (int retry = 0; retry < I2C_BUS_MAX_RETRY_COUNT; retry++) {
        err = operation();
        if (err == ESP_OK) {
            return ESP_OK;
        }
        
        if (retry < I2C_BUS_MAX_RETRY_COUNT - 1) {
            ESP_LOGW(TAG, "%s failed (attempt %d/%d): %s, retrying...", 
                    op_name, retry + 1, I2C_BUS_MAX_RETRY_COUNT, esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(10)); // Небольшая задержка перед retry
        }
    }
    
    ESP_LOGE(TAG, "%s failed after %d attempts: %s", op_name, I2C_BUS_MAX_RETRY_COUNT, esp_err_to_name(err));
    
    // Попытка восстановления шины
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Attempting I²C bus recovery...");
        i2c_bus_recover();
    }
    
    return err;
}

// Предварительные объявления
static esp_err_t i2c_bus_deinit_bus(i2c_bus_id_t bus_id);
static esp_err_t i2c_bus_scan_bus(i2c_bus_id_t bus_id, uint8_t *found_addresses, size_t max_addresses, size_t *found_count);
static esp_err_t i2c_bus_recover_bus(i2c_bus_id_t bus_id);

esp_err_t i2c_bus_init(const i2c_bus_config_t *config) {
    // Для обратной совместимости - инициализация шины 0
    return i2c_bus_init_bus(I2C_BUS_0, config);
}

esp_err_t i2c_bus_init_bus(i2c_bus_id_t bus_id, const i2c_bus_config_t *config) {
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
    
    // Создание mutex для thread-safe доступа
    if (bus->mutex == NULL) {
        ESP_LOGI(TAG, "Creating I²C bus %d mutex...", bus_id);
        bus->mutex = xSemaphoreCreateMutex();
        if (bus->mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create mutex for bus %d", bus_id);
            return ESP_ERR_NO_MEM;
        }
        ESP_LOGI(TAG, "I²C bus %d mutex created", bus_id);
    }
    
    // Сохранение конфигурации
    memcpy(&bus->config, config, sizeof(i2c_bus_config_t));
    
    // Настройка I²C master bus
    ESP_LOGI(TAG, "Configuring I²C master bus %d...", bus_id);
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
    
    ESP_LOGI(TAG, "Creating I²C master bus %d (port=%d, SDA=%d, SCL=%d)...", 
             bus_id, bus_cfg.i2c_port, bus_cfg.sda_io_num, bus_cfg.scl_io_num);
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus->bus_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I²C master bus %d: %s (error code: %d)", 
                 bus_id, esp_err_to_name(err), err);
        vSemaphoreDelete(bus->mutex);
        bus->mutex = NULL;
        return err;
    }
    
    bus->initialized = true;
    ESP_LOGI(TAG, "I²C bus %d initialized successfully: SDA=%d, SCL=%d, speed=%lu Hz", 
            bus_id, config->sda_pin, config->scl_pin, config->clock_speed);
    ESP_LOGI(TAG, "=== I²C Bus %d Init Complete ===", bus_id);
    
    return ESP_OK;
}

esp_err_t i2c_bus_deinit(void) {
    // Для обратной совместимости - деинициализация шины 0
    return i2c_bus_deinit_bus(I2C_BUS_0);
}

static esp_err_t i2c_bus_deinit_bus(i2c_bus_id_t bus_id) {
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    i2c_bus_state_t *bus = &s_buses[bus_id];
    
    if (!bus->initialized) {
        return ESP_OK;
    }
    
    if (bus->bus_handle != NULL) {
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
    
    ESP_LOGI(TAG, "I²C bus %d deinitialized", bus_id);
    return ESP_OK;
}

bool i2c_bus_is_initialized(void) {
    // Для обратной совместимости - проверка шины 0
    return i2c_bus_is_initialized_bus(I2C_BUS_0);
}

bool i2c_bus_is_initialized_bus(i2c_bus_id_t bus_id) {
    if (bus_id >= I2C_BUS_MAX) {
        return false;
    }
    return s_buses[bus_id].initialized;
}

esp_err_t i2c_bus_read(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                      uint8_t *data, size_t data_len, uint32_t timeout_ms) {
    // Для обратной совместимости - чтение с шины 0
    return i2c_bus_read_bus(I2C_BUS_0, device_addr, reg_addr, reg_addr_len, data, data_len, timeout_ms);
}

esp_err_t i2c_bus_read_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                          uint8_t *data, size_t data_len, uint32_t timeout_ms) {
    if (bus_id >= I2C_BUS_MAX) {
        ESP_LOGE(TAG, "Invalid bus_id: %d", bus_id);
        return ESP_ERR_INVALID_ARG;
    }
    
    i2c_bus_state_t *bus = &s_buses[bus_id];
    
    if (!bus->initialized) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (bus->mutex == NULL) {
        ESP_LOGE(TAG, "I²C bus %d mutex is NULL", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (data == NULL || data_len == 0) {
        ESP_LOGE(TAG, "Invalid arguments: data is NULL or data_len is 0");
        return ESP_ERR_INVALID_ARG;
    }
    
    // Захват mutex
    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for bus %d", bus_id);
        return ESP_ERR_TIMEOUT;
    }
    
    // Проверяем, что bus_handle инициализирован
    if (bus->bus_handle == NULL) {
        ESP_LOGE(TAG, "I²C bus %d handle is NULL", bus_id);
        xSemaphoreGive(bus->mutex);
        return ESP_ERR_INVALID_STATE;
    }
    
    esp_err_t err = ESP_OK;
    
    // Создание или получение device handle
    i2c_master_dev_handle_t dev_handle = NULL;
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = device_addr,
        .scl_speed_hz = bus->config.clock_speed,
    };
    
    err = i2c_master_bus_add_device(bus->bus_handle, &dev_cfg, &dev_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add device to bus %d: %s", bus_id, esp_err_to_name(err));
        xSemaphoreGive(bus->mutex);
        return err;
    }
    
    // Запись адреса регистра (если указан)
    if (reg_addr != NULL && reg_addr_len > 0) {
        err = i2c_master_transmit_receive(dev_handle, reg_addr, reg_addr_len, data, data_len, 
                                         pdMS_TO_TICKS(timeout_ms));
    } else {
        // Чтение без указания регистра
        err = i2c_master_receive(dev_handle, data, data_len, pdMS_TO_TICKS(timeout_ms));
    }
    
    // Удаление device handle (в реальной реализации можно кэшировать)
    i2c_master_bus_rm_device(dev_handle);
    
    xSemaphoreGive(bus->mutex);
    
    if (err != ESP_OK) {
        // Понижаем уровень логирования - ошибки чтения могут быть ожидаемыми (датчик не подключен)
        ESP_LOGD(TAG, "I²C read failed on bus %d: %s (addr=0x%02X)", bus_id, esp_err_to_name(err), device_addr);
    }
    
    return err;
}

esp_err_t i2c_bus_write(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                       const uint8_t *data, size_t data_len, uint32_t timeout_ms) {
    // Для обратной совместимости - запись на шину 0
    return i2c_bus_write_bus(I2C_BUS_0, device_addr, reg_addr, reg_addr_len, data, data_len, timeout_ms);
}

esp_err_t i2c_bus_write_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                           const uint8_t *data, size_t data_len, uint32_t timeout_ms) {
    if (bus_id >= I2C_BUS_MAX) {
        ESP_LOGE(TAG, "Invalid bus_id: %d", bus_id);
        return ESP_ERR_INVALID_ARG;
    }
    
    i2c_bus_state_t *bus = &s_buses[bus_id];
    
    if (!bus->initialized) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (bus->mutex == NULL) {
        ESP_LOGE(TAG, "I²C bus %d mutex is NULL", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (data == NULL || data_len == 0) {
        ESP_LOGE(TAG, "Invalid arguments: data is NULL or data_len is 0");
        return ESP_ERR_INVALID_ARG;
    }
    
    ESP_LOGD(TAG, "I²C write on bus %d: addr=0x%02X, reg_len=%zu, data_len=%zu", 
             bus_id, device_addr, reg_addr_len, data_len);
    
    // Захват mutex
    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for bus %d", bus_id);
        return ESP_ERR_TIMEOUT;
    }
    
    // Проверяем, что bus_handle инициализирован
    if (bus->bus_handle == NULL) {
        ESP_LOGE(TAG, "I²C bus %d handle is NULL", bus_id);
        xSemaphoreGive(bus->mutex);
        return ESP_ERR_INVALID_STATE;
    }
    
    esp_err_t err = ESP_OK;
    
    // Создание device handle
    i2c_master_dev_handle_t dev_handle = NULL;
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = device_addr,
        .scl_speed_hz = bus->config.clock_speed,
    };
    
    err = i2c_master_bus_add_device(bus->bus_handle, &dev_cfg, &dev_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add device to bus %d: %s", bus_id, esp_err_to_name(err));
        xSemaphoreGive(bus->mutex);
        return err;
    }
    
    // Формирование буфера для передачи
    size_t total_len = (reg_addr != NULL ? reg_addr_len : 0) + data_len;
    uint8_t *write_buf = malloc(total_len);
    if (write_buf == NULL) {
        ESP_LOGE(TAG, "Failed to allocate write buffer");
        i2c_master_bus_rm_device(dev_handle);
        xSemaphoreGive(bus->mutex);
        return ESP_ERR_NO_MEM;
    }
    
    // Копирование адреса регистра и данных
    if (reg_addr != NULL && reg_addr_len > 0) {
        memcpy(write_buf, reg_addr, reg_addr_len);
    }
    memcpy(write_buf + (reg_addr != NULL ? reg_addr_len : 0), data, data_len);
    
    // Запись
    err = i2c_master_transmit(dev_handle, write_buf, total_len, pdMS_TO_TICKS(timeout_ms));
    
    free(write_buf);
    i2c_master_bus_rm_device(dev_handle);
    xSemaphoreGive(bus->mutex);
    
    if (err != ESP_OK) {
        // Понижаем уровень логирования - ошибки записи могут быть ожидаемыми (датчик не подключен)
        ESP_LOGD(TAG, "I²C write failed on bus %d: %s (addr=0x%02X)", bus_id, esp_err_to_name(err), device_addr);
    }
    
    return err;
}

esp_err_t i2c_bus_read_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t *data, uint32_t timeout_ms) {
    return i2c_bus_read(device_addr, &reg_addr, 1, data, 1, timeout_ms);
}

esp_err_t i2c_bus_write_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t data, uint32_t timeout_ms) {
    return i2c_bus_write(device_addr, &reg_addr, 1, &data, 1, timeout_ms);
}

esp_err_t i2c_bus_scan(uint8_t *found_addresses, size_t max_addresses, size_t *found_count) {
    // Для обратной совместимости - сканирование шины 0
    return i2c_bus_scan_bus(I2C_BUS_0, found_addresses, max_addresses, found_count);
}

static esp_err_t i2c_bus_scan_bus(i2c_bus_id_t bus_id, uint8_t *found_addresses, size_t max_addresses, size_t *found_count) {
    if (bus_id >= I2C_BUS_MAX) {
        ESP_LOGE(TAG, "Invalid bus_id: %d", bus_id);
        return ESP_ERR_INVALID_ARG;
    }
    
    i2c_bus_state_t *bus = &s_buses[bus_id];
    
    if (!bus->initialized) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (bus->mutex == NULL) {
        ESP_LOGE(TAG, "I²C bus %d mutex is NULL", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    if (found_addresses == NULL || found_count == NULL) {
        ESP_LOGE(TAG, "Invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    
    *found_count = 0;
    
    // Захват mutex
    if (xSemaphoreTake(bus->mutex, pdMS_TO_TICKS(5000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for bus %d", bus_id);
        return ESP_ERR_TIMEOUT;
    }
    
    // Проверяем, что bus_handle инициализирован
    if (bus->bus_handle == NULL) {
        ESP_LOGE(TAG, "I²C bus %d handle is NULL", bus_id);
        xSemaphoreGive(bus->mutex);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Сканирование адресов 0x08-0x77 (валидные I²C адреса)
    for (uint8_t addr = 0x08; addr < 0x78 && *found_count < max_addresses; addr++) {
        i2c_master_dev_handle_t dev_handle = NULL;
        i2c_device_config_t dev_cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = addr,
            .scl_speed_hz = bus->config.clock_speed,
        };
        
        esp_err_t err = i2c_master_bus_add_device(bus->bus_handle, &dev_cfg, &dev_handle);
        if (err == ESP_OK) {
            // Попытка чтения для проверки наличия устройства
            uint8_t dummy;
            err = i2c_master_receive(dev_handle, &dummy, 1, pdMS_TO_TICKS(100));
            if (err == ESP_OK) {
                found_addresses[*found_count] = addr;
                (*found_count)++;
                ESP_LOGI(TAG, "Found I²C device at address 0x%02X on bus %d", addr, bus_id);
            }
            i2c_master_bus_rm_device(dev_handle);
        }
    }
    
    xSemaphoreGive(bus->mutex);
    
    ESP_LOGI(TAG, "I²C bus %d scan completed: found %zu device(s)", bus_id, *found_count);
    return ESP_OK;
}

esp_err_t i2c_bus_recover(void) {
    // Для обратной совместимости - восстановление шины 0
    return i2c_bus_recover_bus(I2C_BUS_0);
}

static esp_err_t i2c_bus_recover_bus(i2c_bus_id_t bus_id) {
    if (bus_id >= I2C_BUS_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    
    i2c_bus_state_t *bus = &s_buses[bus_id];
    
    if (!bus->initialized) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    ESP_LOGI(TAG, "Recovering I²C bus %d...", bus_id);
    
    // Сохранение конфигурации
    i2c_bus_config_t saved_config;
    memcpy(&saved_config, &bus->config, sizeof(i2c_bus_config_t));
    
    // Деинициализация
    i2c_bus_deinit_bus(bus_id);
    
    // Небольшая задержка
    vTaskDelay(pdMS_TO_TICKS(100));
    
    // Повторная инициализация с теми же параметрами
    esp_err_t err = i2c_bus_init_bus(bus_id, &saved_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to reinitialize I²C bus %d after recovery", bus_id);
        return err;
    }
    
    ESP_LOGI(TAG, "I²C bus %d recovered successfully", bus_id);
    return ESP_OK;
}

esp_err_t i2c_bus_init_from_config(void) {
    // Загрузка конфигурации из NodeConfig
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to load config from storage, using defaults");
        // Использование значений по умолчанию
        i2c_bus_config_t default_config = {
            .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
            .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
            .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
            .pullup_enable = true
        };
        return i2c_bus_init(&default_config);
    }
    
    // Парсинг JSON
    cJSON *config = cJSON_Parse(config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        // Использование значений по умолчанию
        i2c_bus_config_t default_config = {
            .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
            .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
            .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
            .pullup_enable = true
        };
        return i2c_bus_init(&default_config);
    }
    
    // Извлечение hardware.i2c секции
    cJSON *hardware = cJSON_GetObjectItem(config, "hardware");
    if (hardware == NULL || !cJSON_IsObject(hardware)) {
        ESP_LOGW(TAG, "No hardware section in config, using defaults");
        cJSON_Delete(config);
        i2c_bus_config_t default_config = {
            .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
            .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
            .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
            .pullup_enable = true
        };
        return i2c_bus_init(&default_config);
    }
    
    cJSON *i2c = cJSON_GetObjectItem(hardware, "i2c");
    if (i2c == NULL || !cJSON_IsObject(i2c)) {
        ESP_LOGW(TAG, "No i2c section in hardware, using defaults");
        cJSON_Delete(config);
        i2c_bus_config_t default_config = {
            .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
            .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
            .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
            .pullup_enable = true
        };
        return i2c_bus_init(&default_config);
    }
    
    // Извлечение параметров
    i2c_bus_config_t i2c_config = {
        .sda_pin = I2C_BUS_DEFAULT_SDA_PIN,
        .scl_pin = I2C_BUS_DEFAULT_SCL_PIN,
        .clock_speed = I2C_BUS_DEFAULT_CLOCK_SPEED,
        .pullup_enable = true
    };
    
    cJSON *item;
    if ((item = cJSON_GetObjectItem(i2c, "sda")) && cJSON_IsNumber(item)) {
        i2c_config.sda_pin = (int)cJSON_GetNumberValue(item);
    }
    
    if ((item = cJSON_GetObjectItem(i2c, "scl")) && cJSON_IsNumber(item)) {
        i2c_config.scl_pin = (int)cJSON_GetNumberValue(item);
    }
    
    if ((item = cJSON_GetObjectItem(i2c, "speed")) && cJSON_IsNumber(item)) {
        i2c_config.clock_speed = (uint32_t)cJSON_GetNumberValue(item);
    }
    
    ESP_LOGI(TAG, "Initializing I²C bus from NodeConfig: SDA=%d, SCL=%d, speed=%lu Hz",
            i2c_config.sda_pin, i2c_config.scl_pin, i2c_config.clock_speed);
    
    // Сохраняем результат инициализации перед удалением config
    esp_err_t result = i2c_bus_init(&i2c_config);
    
    // Освобождаем память в любом случае
    cJSON_Delete(config);
    
    return result;
}

