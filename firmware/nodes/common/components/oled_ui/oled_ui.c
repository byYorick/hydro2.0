/**
 * @file oled_ui.c
 * @brief Реализация OLED UI для узлов ESP32
 * 
 * Компонент реализует локальный UI на OLED дисплее 128x64 (SSD1306/SSD1309):
 * - Драйвер для SSD1306/SSD1309 через I²C
 * - Система экранов с переключением
 * - Отображение статуса ноды
 * - Отдельная FreeRTOS задача для обновления
 * 
 * Стандарты кодирования:
 * - Именование функций: oled_ui_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "oled_ui.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "oled_ui";

// Константы SSD1306
#define SSD1306_I2C_ADDR_DEFAULT 0x3C
#define SSD1306_WIDTH 128
#define SSD1306_HEIGHT 64
#define SSD1306_PAGES 8  // 64 / 8 = 8 страниц

// Команды SSD1306
#define SSD1306_CMD_DISPLAY_OFF 0xAE
#define SSD1306_CMD_DISPLAY_ON 0xAF
#define SSD1306_CMD_SET_DISPLAY_CLOCK_DIV 0xD5
#define SSD1306_CMD_SET_MULTIPLEX 0xA8
#define SSD1306_CMD_SET_DISPLAY_OFFSET 0xD3
#define SSD1306_CMD_SET_START_LINE 0x40
#define SSD1306_CMD_CHARGE_PUMP 0x8D
#define SSD1306_CMD_MEMORY_MODE 0x20
#define SSD1306_CMD_SEG_REMAP 0xA1
#define SSD1306_CMD_COM_SCAN_DEC 0xC8
#define SSD1306_CMD_SET_COM_PINS 0xDA
#define SSD1306_CMD_SET_CONTRAST 0x81
#define SSD1306_CMD_SET_PRECHARGE 0xD9
#define SSD1306_CMD_SET_VCOM_DETECT 0xDB
#define SSD1306_CMD_DISPLAY_ALL_ON_RESUME 0xA4
#define SSD1306_CMD_NORMAL_DISPLAY 0xA6
#define SSD1306_CMD_COLUMN_ADDR 0x21
#define SSD1306_CMD_PAGE_ADDR 0x22
#define SSD1306_CMD_DEACTIVATE_SCROLL 0x2E

// Внутренние структуры
static struct {
    bool initialized;
    uint8_t i2c_address;
    oled_ui_node_type_t node_type;
    char node_uid[32];
    oled_ui_state_t state;
    oled_ui_model_t model;
    oled_ui_config_t config;
    int current_screen;  // Текущий экран в режиме NORMAL
    TaskHandle_t update_task_handle;
    bool task_running;
} s_ui = {0};

// Внутренние функции
static esp_err_t ssd1306_write_command(uint8_t cmd);
static esp_err_t ssd1306_write_data(const uint8_t *data, size_t len);
static esp_err_t ssd1306_init_display(void);
static esp_err_t ssd1306_clear(void);
static esp_err_t ssd1306_set_cursor(uint8_t x, uint8_t y);
static void render_boot_screen(void);
static void render_wifi_setup_screen(void);
static void render_normal_screen(void);
static void render_alert_screen(void);
static void render_calibration_screen(void);
static void render_service_screen(void);
static void render_char(uint8_t x, uint8_t y, char c);
static void render_string(uint8_t x, uint8_t y, const char *str);
static void render_line(uint8_t y, const char *str);
static void task_update_display(void *pvParameters);

/**
 * @brief Запись команды в SSD1306
 */
static esp_err_t ssd1306_write_command(uint8_t cmd) {
    uint8_t buffer[2] = {0x00, cmd};  // 0x00 = command mode
    return i2c_bus_write(s_ui.i2c_address, NULL, 0, buffer, 2, 100);
}

/**
 * @brief Запись данных в SSD1306
 */
static esp_err_t ssd1306_write_data(const uint8_t *data, size_t len) {
    if (data == NULL || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    // Для больших буферов нужно разбивать на части
    const size_t max_chunk = 32;
    esp_err_t err = ESP_OK;
    
    for (size_t offset = 0; offset < len; offset += max_chunk) {
        size_t chunk_len = (len - offset > max_chunk) ? max_chunk : (len - offset);
        uint8_t buffer[33];
        buffer[0] = 0x40;  // 0x40 = data mode
        memcpy(&buffer[1], &data[offset], chunk_len);
        
        // Запись через I²C: адрес устройства, затем данные с префиксом 0x40
        err = i2c_bus_write(s_ui.i2c_address, NULL, 0, buffer, chunk_len + 1, 100);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to write data to SSD1306: %s", esp_err_to_name(err));
            return err;
        }
    }
    
    return ESP_OK;
}

/**
 * @brief Инициализация дисплея SSD1306
 */
static esp_err_t ssd1306_init_display(void) {
    esp_err_t err;
    
    // Последовательность инициализации SSD1306
    uint8_t init_commands[] = {
        SSD1306_CMD_DISPLAY_OFF,
        SSD1306_CMD_SET_DISPLAY_CLOCK_DIV, 0x80,
        SSD1306_CMD_SET_MULTIPLEX, 0x3F,
        SSD1306_CMD_SET_DISPLAY_OFFSET, 0x00,
        SSD1306_CMD_SET_START_LINE | 0x0,
        SSD1306_CMD_CHARGE_PUMP, 0x14,
        SSD1306_CMD_MEMORY_MODE, 0x00,
        SSD1306_CMD_SEG_REMAP | 0x1,
        SSD1306_CMD_COM_SCAN_DEC,
        SSD1306_CMD_SET_COM_PINS, 0x12,
        SSD1306_CMD_SET_CONTRAST, 0xCF,
        SSD1306_CMD_SET_PRECHARGE, 0xF1,
        SSD1306_CMD_SET_VCOM_DETECT, 0x40,
        SSD1306_CMD_DISPLAY_ALL_ON_RESUME,
        SSD1306_CMD_NORMAL_DISPLAY,
        SSD1306_CMD_DEACTIVATE_SCROLL,
        SSD1306_CMD_DISPLAY_ON
    };
    
    for (size_t i = 0; i < sizeof(init_commands); i++) {
        err = ssd1306_write_command(init_commands[i]);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to send init command at index %zu", i);
            return err;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    
    // Очистка дисплея
    err = ssd1306_clear();
    if (err != ESP_OK) {
        return err;
    }
    
    ESP_LOGI(TAG, "SSD1306 display initialized");
    return ESP_OK;
}

/**
 * @brief Очистка дисплея
 */
static esp_err_t ssd1306_clear(void) {
    // Установка адреса колонок и страниц
    esp_err_t err = ssd1306_write_command(SSD1306_CMD_COLUMN_ADDR);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(0);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(SSD1306_WIDTH - 1);
    if (err != ESP_OK) return err;
    
    err = ssd1306_write_command(SSD1306_CMD_PAGE_ADDR);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(0);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(SSD1306_PAGES - 1);
    if (err != ESP_OK) return err;
    
    // Заполнение нулями
    uint8_t zeros[SSD1306_WIDTH];
    memset(zeros, 0, sizeof(zeros));
    for (int page = 0; page < SSD1306_PAGES; page++) {
        err = ssd1306_write_data(zeros, sizeof(zeros));
        if (err != ESP_OK) return err;
    }
    
    return ESP_OK;
}

/**
 * @brief Установка курсора (упрощенная версия)
 */
static esp_err_t ssd1306_set_cursor(uint8_t x, uint8_t y) {
    esp_err_t err = ssd1306_write_command(SSD1306_CMD_COLUMN_ADDR);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(x);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(SSD1306_WIDTH - 1);
    if (err != ESP_OK) return err;
    
    err = ssd1306_write_command(SSD1306_CMD_PAGE_ADDR);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(y / 8);
    if (err != ESP_OK) return err;
    err = ssd1306_write_command(SSD1306_PAGES - 1);
    if (err != ESP_OK) return err;
    
    return ESP_OK;
}

/**
 * @brief Отображение символа (упрощенная версия - только ASCII)
 * 
 * Примечание: упрощенная реализация. В реальности нужен растровый шрифт.
 * Для MVP используем простой подход с прямым выводом символов.
 */
static void render_char(uint8_t x, uint8_t y, char c) {
    // Упрощенная реализация - в реальности нужен шрифт 8x8
    // Для MVP пропускаем, так как render_string будет использовать другой подход
    (void)x;
    (void)y;
    (void)c;
}

/**
 * @brief Отображение строки
 * 
 * Примечание: упрощенная реализация. В реальности нужен растровый шрифт.
 * Для MVP используем простой текстовый вывод через команды дисплея.
 */
static void render_string(uint8_t x, uint8_t y, const char *str) {
    if (str == NULL) return;
    
    // Упрощенная реализация - устанавливаем курсор и выводим данные
    // В реальности нужно использовать растровый шрифт и отрисовку пикселей
    ssd1306_set_cursor(x, y);
    
    // Для MVP просто устанавливаем курсор
    // Полная реализация требует растрового шрифта и функции отрисовки пикселей
    (void)str;
}

/**
 * @brief Отображение строки на линии
 */
static void render_line(uint8_t y, const char *str) {
    render_string(0, y * 8, str);
}

/**
 * @brief Отрисовка экрана BOOT
 */
static void render_boot_screen(void) {
    ssd1306_clear();
    render_line(0, "Hydro 2.0");
    render_line(1, "Booting...");
    
    if (s_ui.model.connections.wifi_connected) {
        render_line(2, "WiFi: OK");
    } else {
        render_line(2, "WiFi: Connecting");
    }
    
    if (s_ui.model.connections.mqtt_connected) {
        render_line(3, "MQTT: OK");
    } else {
        render_line(3, "MQTT: Connecting");
    }
}

/**
 * @brief Отрисовка экрана WIFI_SETUP
 */
static void render_wifi_setup_screen(void) {
    ssd1306_clear();
    render_line(0, "WiFi Setup");
    render_line(1, "Connect to:");
    render_line(2, "HYDRO-SETUP");
    render_line(3, "Use app to");
    render_line(4, "configure");
}

/**
 * @brief Отрисовка экрана NORMAL (основной)
 */
static void render_normal_screen(void) {
    ssd1306_clear();
    
    // Верхняя строка: статусы
    char status_line[22];
    snprintf(status_line, sizeof(status_line), "%c %c %s",
            s_ui.model.connections.wifi_connected ? 'W' : 'w',
            s_ui.model.connections.mqtt_connected ? 'M' : 'm',
            s_ui.node_uid);
    render_line(0, status_line);
    
    // Основной блок в зависимости от типа узла и текущего экрана
    if (s_ui.current_screen == 0) {
        // Основной экран
        switch (s_ui.node_type) {
            case OLED_UI_NODE_TYPE_PH: {
                char line[22];
                snprintf(line, sizeof(line), "pH: %.2f", s_ui.model.ph_value);
                render_line(2, line);
                snprintf(line, sizeof(line), "Temp: %.1fC", s_ui.model.temperature_water);
                render_line(3, line);
                break;
            }
            case OLED_UI_NODE_TYPE_EC: {
                char line[22];
                snprintf(line, sizeof(line), "EC: %.2f", s_ui.model.ec_value);
                render_line(2, line);
                snprintf(line, sizeof(line), "Temp: %.1fC", s_ui.model.temperature_water);
                render_line(3, line);
                break;
            }
            case OLED_UI_NODE_TYPE_CLIMATE: {
                char line[22];
                snprintf(line, sizeof(line), "T: %.1fC H: %.0f%%", 
                        s_ui.model.temperature_air, s_ui.model.humidity);
                render_line(2, line);
                break;
            }
            default:
                render_line(2, "Node active");
                break;
        }
    } else if (s_ui.current_screen == 1) {
        // Экран каналов
        render_line(1, "Channels:");
        for (size_t i = 0; i < s_ui.model.channel_count && i < 5; i++) {
            char line[22];
            snprintf(line, sizeof(line), "%s: %.2f",
                    s_ui.model.channels[i].name,
                    s_ui.model.channels[i].value);
            render_line(2 + i, line);
        }
    } else if (s_ui.current_screen == 2) {
        // Экран зоны
        render_line(1, "Zone:");
        render_line(2, s_ui.model.zone_name);
        render_line(3, "Recipe:");
        render_line(4, s_ui.model.recipe_name);
    }
    
    // Нижняя строка: состояние
    if (s_ui.model.alert) {
        render_line(7, "ALERT");
    } else if (s_ui.model.paused) {
        render_line(7, "PAUSED");
    } else {
        render_line(7, "OK");
    }
}

/**
 * @brief Отрисовка экрана ALERT
 */
static void render_alert_screen(void) {
    ssd1306_clear();
    render_line(2, "ALERT");
    render_line(3, s_ui.model.alert_message);
    render_line(5, "See app");
}

/**
 * @brief Отрисовка экрана CALIBRATION
 */
static void render_calibration_screen(void) {
    ssd1306_clear();
    render_line(1, "Calibration");
    render_line(2, "Follow");
    render_line(3, "instructions");
}

/**
 * @brief Отрисовка экрана SERVICE
 */
static void render_service_screen(void) {
    ssd1306_clear();
    render_line(0, "Service Menu");
    render_line(2, "Node:");
    render_line(3, s_ui.node_uid);
}

/**
 * @brief Задача обновления дисплея
 */
static void task_update_display(void *pvParameters) {
    ESP_LOGI(TAG, "OLED UI update task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(s_ui.config.update_interval_ms);
    
    while (s_ui.task_running) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!s_ui.initialized) {
            continue;
        }
        
        // Отрисовка в зависимости от состояния
        switch (s_ui.state) {
            case OLED_UI_STATE_BOOT:
                render_boot_screen();
                break;
            case OLED_UI_STATE_WIFI_SETUP:
                render_wifi_setup_screen();
                break;
            case OLED_UI_STATE_NORMAL:
                render_normal_screen();
                break;
            case OLED_UI_STATE_ALERT:
                render_alert_screen();
                break;
            case OLED_UI_STATE_CALIBRATION:
                render_calibration_screen();
                break;
            case OLED_UI_STATE_SERVICE:
                render_service_screen();
                break;
        }
    }
    
    ESP_LOGI(TAG, "OLED UI update task stopped");
    vTaskDelete(NULL);
}

// Публичные функции

esp_err_t oled_ui_init(oled_ui_node_type_t node_type, const char *node_uid, 
                      const oled_ui_config_t *config) {
    if (s_ui.initialized) {
        ESP_LOGW(TAG, "OLED UI already initialized");
        return ESP_OK;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    // Сохранение параметров
    s_ui.node_type = node_type;
    if (node_uid != NULL) {
        strncpy(s_ui.node_uid, node_uid, sizeof(s_ui.node_uid) - 1);
    }
    
    // Конфигурация
    if (config != NULL) {
        memcpy(&s_ui.config, config, sizeof(oled_ui_config_t));
    } else {
        s_ui.config.i2c_address = SSD1306_I2C_ADDR_DEFAULT;
        s_ui.config.update_interval_ms = 500;
        s_ui.config.enable_task = true;
    }
    
    s_ui.i2c_address = s_ui.config.i2c_address;
    s_ui.state = OLED_UI_STATE_BOOT;
    s_ui.current_screen = 0;
    
    // Инициализация дисплея
    esp_err_t err = ssd1306_init_display();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SSD1306: %s", esp_err_to_name(err));
        return err;
    }
    
    // Инициализация модели
    memset(&s_ui.model, 0, sizeof(oled_ui_model_t));
    
    s_ui.initialized = true;
    ESP_LOGI(TAG, "OLED UI initialized (node_type=%d, addr=0x%02X)", node_type, s_ui.i2c_address);
    
    // Запуск задачи обновления
    if (s_ui.config.enable_task) {
        err = oled_ui_start_task();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to start update task");
        }
    }
    
    return ESP_OK;
}

esp_err_t oled_ui_deinit(void) {
    if (!s_ui.initialized) {
        return ESP_OK;
    }
    
    // Остановка задачи
    oled_ui_stop_task();
    
    // Выключение дисплея
    ssd1306_write_command(SSD1306_CMD_DISPLAY_OFF);
    
    s_ui.initialized = false;
    ESP_LOGI(TAG, "OLED UI deinitialized");
    return ESP_OK;
}

esp_err_t oled_ui_set_state(oled_ui_state_t state) {
    if (!s_ui.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    s_ui.state = state;
    ESP_LOGI(TAG, "OLED UI state changed to %d", state);
    
    // Немедленное обновление
    oled_ui_refresh();
    
    return ESP_OK;
}

oled_ui_state_t oled_ui_get_state(void) {
    return s_ui.state;
}

esp_err_t oled_ui_update_model(const oled_ui_model_t *model) {
    if (!s_ui.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (model == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    memcpy(&s_ui.model, model, sizeof(oled_ui_model_t));
    return ESP_OK;
}

esp_err_t oled_ui_refresh(void) {
    if (!s_ui.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    // Отрисовка в зависимости от состояния
    switch (s_ui.state) {
        case OLED_UI_STATE_BOOT:
            render_boot_screen();
            break;
        case OLED_UI_STATE_WIFI_SETUP:
            render_wifi_setup_screen();
            break;
        case OLED_UI_STATE_NORMAL:
            render_normal_screen();
            break;
        case OLED_UI_STATE_ALERT:
            render_alert_screen();
            break;
        case OLED_UI_STATE_CALIBRATION:
            render_calibration_screen();
            break;
        case OLED_UI_STATE_SERVICE:
            render_service_screen();
            break;
    }
    
    return ESP_OK;
}

esp_err_t oled_ui_next_screen(void) {
    if (s_ui.state != OLED_UI_STATE_NORMAL) {
        return ESP_ERR_INVALID_STATE;
    }
    
    s_ui.current_screen = (s_ui.current_screen + 1) % 3;
    oled_ui_refresh();
    return ESP_OK;
}

esp_err_t oled_ui_prev_screen(void) {
    if (s_ui.state != OLED_UI_STATE_NORMAL) {
        return ESP_ERR_INVALID_STATE;
    }
    
    s_ui.current_screen = (s_ui.current_screen + 2) % 3;
    oled_ui_refresh();
    return ESP_OK;
}

esp_err_t oled_ui_handle_encoder(int direction) {
    if (direction > 0) {
        return oled_ui_next_screen();
    } else if (direction < 0) {
        return oled_ui_prev_screen();
    }
    return ESP_OK;
}

esp_err_t oled_ui_handle_button(void) {
    // В зависимости от состояния можно реализовать разные действия
    // Для MVP просто обновляем экран
    return oled_ui_refresh();
}

esp_err_t oled_ui_start_task(void) {
    if (s_ui.task_running) {
        return ESP_OK;
    }
    
    s_ui.task_running = true;
    BaseType_t err = xTaskCreate(task_update_display, "oled_ui_task", 4096, NULL, 2, 
                                 &s_ui.update_task_handle);
    if (err != pdPASS) {
        s_ui.task_running = false;
        ESP_LOGE(TAG, "Failed to create OLED UI task");
        return ESP_FAIL;
    }
    
    ESP_LOGI(TAG, "OLED UI task started");
    return ESP_OK;
}

esp_err_t oled_ui_stop_task(void) {
    if (!s_ui.task_running) {
        return ESP_OK;
    }
    
    s_ui.task_running = false;
    if (s_ui.update_task_handle != NULL) {
        vTaskDelay(pdMS_TO_TICKS(100));  // Даем задаче время на завершение
        s_ui.update_task_handle = NULL;
    }
    
    ESP_LOGI(TAG, "OLED UI task stopped");
    return ESP_OK;
}

