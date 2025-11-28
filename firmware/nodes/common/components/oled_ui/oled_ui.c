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
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

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

// Размер шрифта
#define FONT_WIDTH 6
#define FONT_HEIGHT 8

// Базовый растровый шрифт 6x8 (ASCII 32-127)
static const uint8_t font_6x8[][6] = {
    {0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, // space (32)
    {0x00, 0x00, 0x5F, 0x00, 0x00, 0x00}, // !
    {0x00, 0x07, 0x00, 0x07, 0x00, 0x00}, // "
    {0x14, 0x7F, 0x14, 0x7F, 0x14, 0x00}, // #
    {0x24, 0x2A, 0x7F, 0x2A, 0x12, 0x00}, // $
    {0x23, 0x13, 0x08, 0x64, 0x62, 0x00}, // %
    {0x36, 0x49, 0x55, 0x22, 0x50, 0x00}, // &
    {0x00, 0x05, 0x03, 0x00, 0x00, 0x00}, // '
    {0x00, 0x1C, 0x22, 0x41, 0x00, 0x00}, // (
    {0x00, 0x41, 0x22, 0x1C, 0x00, 0x00}, // )
    {0x14, 0x08, 0x3E, 0x08, 0x14, 0x00}, // *
    {0x08, 0x08, 0x3E, 0x08, 0x08, 0x00}, // +
    {0x00, 0x00, 0xA0, 0x60, 0x00, 0x00}, // ,
    {0x08, 0x08, 0x08, 0x08, 0x08, 0x00}, // -
    {0x00, 0x60, 0x60, 0x00, 0x00, 0x00}, // .
    {0x20, 0x10, 0x08, 0x04, 0x02, 0x00}, // /
    {0x3E, 0x51, 0x49, 0x45, 0x3E, 0x00}, // 0 (48)
    {0x00, 0x42, 0x7F, 0x40, 0x00, 0x00}, // 1
    {0x42, 0x61, 0x51, 0x49, 0x46, 0x00}, // 2
    {0x21, 0x41, 0x45, 0x4B, 0x31, 0x00}, // 3
    {0x18, 0x14, 0x12, 0x7F, 0x10, 0x00}, // 4
    {0x27, 0x45, 0x45, 0x45, 0x39, 0x00}, // 5
    {0x3C, 0x4A, 0x49, 0x49, 0x30, 0x00}, // 6
    {0x01, 0x71, 0x09, 0x05, 0x03, 0x00}, // 7
    {0x36, 0x49, 0x49, 0x49, 0x36, 0x00}, // 8
    {0x06, 0x49, 0x49, 0x29, 0x1E, 0x00}, // 9
    {0x00, 0x36, 0x36, 0x00, 0x00, 0x00}, // :
    {0x00, 0x56, 0x36, 0x00, 0x00, 0x00}, // ;
    {0x08, 0x14, 0x22, 0x41, 0x00, 0x00}, // <
    {0x14, 0x14, 0x14, 0x14, 0x14, 0x00}, // =
    {0x00, 0x41, 0x22, 0x14, 0x08, 0x00}, // >
    {0x02, 0x01, 0x51, 0x09, 0x06, 0x00}, // ?
    {0x32, 0x49, 0x59, 0x51, 0x3E, 0x00}, // @
    {0x7C, 0x12, 0x11, 0x12, 0x7C, 0x00}, // A (65)
    {0x7F, 0x49, 0x49, 0x49, 0x36, 0x00}, // B
    {0x3E, 0x41, 0x41, 0x41, 0x22, 0x00}, // C
    {0x7F, 0x41, 0x41, 0x22, 0x1C, 0x00}, // D
    {0x7F, 0x49, 0x49, 0x49, 0x41, 0x00}, // E
    {0x7F, 0x09, 0x09, 0x09, 0x01, 0x00}, // F
    {0x3E, 0x41, 0x49, 0x49, 0x7A, 0x00}, // G
    {0x7F, 0x08, 0x08, 0x08, 0x7F, 0x00}, // H
    {0x00, 0x41, 0x7F, 0x41, 0x00, 0x00}, // I
    {0x20, 0x40, 0x41, 0x3F, 0x01, 0x00}, // J
    {0x7F, 0x08, 0x14, 0x22, 0x41, 0x00}, // K
    {0x7F, 0x40, 0x40, 0x40, 0x40, 0x00}, // L
    {0x7F, 0x02, 0x0C, 0x02, 0x7F, 0x00}, // M
    {0x7F, 0x04, 0x08, 0x10, 0x7F, 0x00}, // N
    {0x3E, 0x41, 0x41, 0x41, 0x3E, 0x00}, // O
    {0x7F, 0x09, 0x09, 0x09, 0x06, 0x00}, // P
    {0x3E, 0x41, 0x51, 0x21, 0x5E, 0x00}, // Q
    {0x7F, 0x09, 0x19, 0x29, 0x46, 0x00}, // R
    {0x46, 0x49, 0x49, 0x49, 0x31, 0x00}, // S
    {0x01, 0x01, 0x7F, 0x01, 0x01, 0x00}, // T
    {0x3F, 0x40, 0x40, 0x40, 0x3F, 0x00}, // U
    {0x1F, 0x20, 0x40, 0x20, 0x1F, 0x00}, // V
    {0x3F, 0x40, 0x38, 0x40, 0x3F, 0x00}, // W
    {0x63, 0x14, 0x08, 0x14, 0x63, 0x00}, // X
    {0x07, 0x08, 0x70, 0x08, 0x07, 0x00}, // Y
    {0x61, 0x51, 0x49, 0x45, 0x43, 0x00}, // Z
    {0x00, 0x7F, 0x41, 0x41, 0x00, 0x00}, // [
    {0x02, 0x04, 0x08, 0x10, 0x20, 0x00}, // backslash
    {0x00, 0x41, 0x41, 0x7F, 0x00, 0x00}, // ]
    {0x04, 0x02, 0x01, 0x02, 0x04, 0x00}, // ^
    {0x40, 0x40, 0x40, 0x40, 0x40, 0x00}, // _
    {0x00, 0x01, 0x02, 0x04, 0x00, 0x00}, // `
    {0x20, 0x54, 0x54, 0x54, 0x78, 0x00}, // a (97)
    {0x7F, 0x48, 0x44, 0x44, 0x38, 0x00}, // b
    {0x38, 0x44, 0x44, 0x44, 0x20, 0x00}, // c
    {0x38, 0x44, 0x44, 0x48, 0x7F, 0x00}, // d
    {0x38, 0x54, 0x54, 0x54, 0x18, 0x00}, // e
    {0x08, 0x7E, 0x09, 0x01, 0x02, 0x00}, // f
    {0x18, 0xA4, 0xA4, 0xA4, 0x7C, 0x00}, // g
    {0x7F, 0x08, 0x04, 0x04, 0x78, 0x00}, // h
    {0x00, 0x44, 0x7D, 0x40, 0x00, 0x00}, // i
    {0x40, 0x80, 0x84, 0x7D, 0x00, 0x00}, // j
    {0x7F, 0x10, 0x28, 0x44, 0x00, 0x00}, // k
    {0x00, 0x41, 0x7F, 0x40, 0x00, 0x00}, // l
    {0x7C, 0x04, 0x18, 0x04, 0x78, 0x00}, // m
    {0x7C, 0x08, 0x04, 0x04, 0x78, 0x00}, // n
    {0x38, 0x44, 0x44, 0x44, 0x38, 0x00}, // o
    {0xFC, 0x24, 0x24, 0x24, 0x18, 0x00}, // p
    {0x18, 0x24, 0x24, 0x18, 0xFC, 0x00}, // q
    {0x7C, 0x08, 0x04, 0x04, 0x08, 0x00}, // r
    {0x48, 0x54, 0x54, 0x54, 0x20, 0x00}, // s
    {0x04, 0x3F, 0x44, 0x40, 0x20, 0x00}, // t
    {0x3C, 0x40, 0x40, 0x20, 0x7C, 0x00}, // u
    {0x1C, 0x20, 0x40, 0x20, 0x1C, 0x00}, // v
    {0x3C, 0x40, 0x30, 0x40, 0x3C, 0x00}, // w
    {0x44, 0x28, 0x10, 0x28, 0x44, 0x00}, // x
    {0x1C, 0xA0, 0xA0, 0xA0, 0x7C, 0x00}, // y
    {0x44, 0x64, 0x54, 0x4C, 0x44, 0x00}, // z
    {0x00, 0x08, 0x36, 0x41, 0x00, 0x00}, // {
    {0x00, 0x00, 0x7F, 0x00, 0x00, 0x00}, // |
    {0x00, 0x41, 0x36, 0x08, 0x00, 0x00}, // }
    {0x10, 0x08, 0x08, 0x10, 0x08, 0x00}, // ~
    {0x78, 0x46, 0x41, 0x46, 0x78, 0x00}, // DEL (127)
};

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
    
    // Шаги инициализации
    bool init_steps_active;
    int current_step_num;
    char current_step_text[32];
    TaskHandle_t init_animation_task;
    bool init_animation_active;
    int init_dot_count;  // Текущее количество точек для анимации (0-3)
    
    // Mutex для защиты операций отрисовки
    SemaphoreHandle_t render_mutex;
    
    // Флаги мигания для MQTT активности
    bool mqtt_tx_active;  // Флаг активности отправки
    bool mqtt_rx_active;  // Флаг активности приема
    uint64_t mqtt_tx_timestamp;  // Время последней отправки
    uint64_t mqtt_rx_timestamp;  // Время последнего приема
    
    // Буфер кадров для устранения мерцания (128x64 = 1024 байта)
    uint8_t frame_buffer[SSD1306_WIDTH * SSD1306_PAGES];
} s_ui = {0};

// Внутренние функции
static esp_err_t ssd1306_write_command(uint8_t cmd);
static esp_err_t ssd1306_write_data(const uint8_t *data, size_t len);
static esp_err_t ssd1306_init_display(void);
static esp_err_t ssd1306_clear(void);
static esp_err_t ssd1306_set_cursor(uint8_t x, uint8_t y);
static esp_err_t ssd1306_update_display(void);  // Отправка всего буфера на дисплей
static void frame_buffer_clear(void);  // Очистка буфера кадров
static void frame_buffer_set_pixel(uint8_t x, uint8_t y, bool on);  // Установка пикселя в буфере
static void frame_buffer_draw_char(uint8_t x, uint8_t y, uint8_t c);  // Отрисовка символа в буфере
static void frame_buffer_draw_string(uint8_t x, uint8_t y, const char *str);  // Отрисовка строки в буфере
static void frame_buffer_draw_line(uint8_t line_num, const char *str);  // Отрисовка строки на линии в буфере
static void frame_buffer_draw_wifi_icon(uint8_t x, uint8_t y, int8_t rssi);  // Отрисовка иконки WiFi в буфере
static void render_boot_screen(void);
static void render_wifi_setup_screen(void);
static void render_normal_screen(void);
static void render_alert_screen(void);
static void render_calibration_screen(void);
static void render_service_screen(void);
static const uint8_t* get_char_glyph(uint8_t c);
static void render_char(uint8_t x, uint8_t y, uint8_t c);
static void render_string(uint8_t x, uint8_t y, const char *str);
static void render_line(uint8_t line_num, const char *str);
static void render_wifi_icon(uint8_t x, uint8_t y, int8_t rssi);
static void task_update_display(void *pvParameters);

/**
 * @brief Запись команды в SSD1306
 */
static esp_err_t ssd1306_write_command(uint8_t cmd) {
    uint8_t buffer[2] = {0x00, cmd};  // 0x00 = command mode
    esp_err_t err = i2c_bus_write(s_ui.i2c_address, NULL, 0, buffer, 2, 1000);  // Увеличено с 100 до 1000 мс
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to write command 0x%02X to SSD1306: %s", cmd, esp_err_to_name(err));
    }
    return err;
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
        err = i2c_bus_write(s_ui.i2c_address, NULL, 0, buffer, chunk_len + 1, 1000);  // Увеличено с 100 до 1000 мс
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
    
    ESP_LOGI(TAG, "Initializing SSD1306 display at I2C address 0x%02X", s_ui.i2c_address);
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized before SSD1306 init");
        return ESP_ERR_INVALID_STATE;
    }
    
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
    
    ESP_LOGI(TAG, "Sending %d initialization commands to SSD1306", (int)sizeof(init_commands));
    for (size_t i = 0; i < sizeof(init_commands); i++) {
        err = ssd1306_write_command(init_commands[i]);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to send command[%d]=0x%02X: %s", (int)i, init_commands[i], esp_err_to_name(err));
            ESP_LOGE(TAG, "Failed to send init command at index %zu", i);
            return err;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    
    // Очистка буфера кадров и отправка на дисплей
    frame_buffer_clear();
    err = ssd1306_update_display();
    if (err != ESP_OK) {
        return err;
    }
    
    ESP_LOGI(TAG, "SSD1306 display initialized");
    return ESP_OK;
}

/**
 * @brief Очистка дисплея
 */
__attribute__((unused)) static esp_err_t ssd1306_clear(void) {
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
__attribute__((unused)) static esp_err_t ssd1306_set_cursor(uint8_t x, uint8_t y) {
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
 * @brief Отправка всего буфера кадров на дисплей
 * 
 * Отправляет весь буфер кадров на дисплей за один раз для устранения мерцания
 */
static esp_err_t ssd1306_update_display(void) {
    // Установка адреса колонок и страниц для всего дисплея
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
    
    // Отправка всего буфера кадров
    err = ssd1306_write_data(s_ui.frame_buffer, sizeof(s_ui.frame_buffer));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to update display: %s", esp_err_to_name(err));
        return err;
    }
    
    return ESP_OK;
}

/**
 * @brief Очистка буфера кадров
 */
static void frame_buffer_clear(void) {
    memset(s_ui.frame_buffer, 0, sizeof(s_ui.frame_buffer));
}

/**
 * @brief Установка пикселя в буфере кадров
 * @param x X координата (0-127)
 * @param y Y координата (0-63)
 * @param on true = включить пиксель, false = выключить
 */
__attribute__((unused)) static void frame_buffer_set_pixel(uint8_t x, uint8_t y, bool on) {
    if (x >= SSD1306_WIDTH || y >= SSD1306_HEIGHT) {
        return;
    }
    
    uint8_t page = y / 8;
    uint8_t bit = y % 8;
    size_t index = page * SSD1306_WIDTH + x;
    
    if (on) {
        s_ui.frame_buffer[index] |= (1 << bit);
    } else {
        s_ui.frame_buffer[index] &= ~(1 << bit);
    }
}

/**
 * @brief Отрисовка символа в буфере кадров
 * @param x X координата (0-127)
 * @param y Y координата (0-63, должна быть кратна 8)
 * @param c Символ для отрисовки
 */
static void frame_buffer_draw_char(uint8_t x, uint8_t y, uint8_t c) {
    if (x >= SSD1306_WIDTH || y >= SSD1306_HEIGHT) {
        return;
    }
    
    const uint8_t *glyph = get_char_glyph(c);
    if (glyph == NULL) {
        return;
    }
    
    uint8_t page = y / 8;
    if (page >= SSD1306_PAGES) {
        return;
    }
    
    // Копируем глиф в буфер кадров
    size_t base_index = page * SSD1306_WIDTH + x;
    for (int i = 0; i < FONT_WIDTH && (x + i) < SSD1306_WIDTH; i++) {
        s_ui.frame_buffer[base_index + i] = glyph[i];
    }
}

/**
 * @brief Отрисовка иконки WiFi в буфере кадров
 * @param x X координата (0-127)
 * @param y Y координата (0-63, должна быть кратна 8)
 * @param rssi RSSI значение в dBm
 */
static void frame_buffer_draw_wifi_icon(uint8_t x, uint8_t y, int8_t rssi) {
    if (x >= SSD1306_WIDTH - 8 || y >= SSD1306_HEIGHT) {
        return;
    }
    
    uint8_t page = y / 8;
    if (page >= SSD1306_PAGES) {
        return;
    }
    
    // Определяем количество полосок на основе RSSI
    int bars = 0;
    bool is_connected = (rssi > -100);
    
    if (is_connected) {
        if (rssi >= -50) {
            bars = 4;
        } else if (rssi >= -60) {
            bars = 3;
        } else if (rssi >= -70) {
            bars = 2;
        } else if (rssi >= -80) {
            bars = 1;
        }
    }
    
    // Создаем данные иконки
    uint8_t icon_data[8] = {0};
    
    if (is_connected && bars > 0) {
        if (bars >= 1) {
            icon_data[7] = 0x18;
        }
        if (bars >= 2) {
            icon_data[6] = 0x3C;
        }
        if (bars >= 3) {
            icon_data[5] = 0x7E;
        }
        if (bars >= 4) {
            icon_data[4] = 0xFF;
        }
    } else {
        // Крестик для отсутствия подключения
        icon_data[0] = 0x81;
        icon_data[1] = 0x42;
        icon_data[2] = 0x24;
        icon_data[3] = 0x18;
        icon_data[4] = 0x18;
        icon_data[5] = 0x24;
        icon_data[6] = 0x42;
        icon_data[7] = 0x81;
    }
    
    // Копируем данные иконки в буфер кадров
    size_t base_index = page * SSD1306_WIDTH + x;
    for (int i = 0; i < 8 && (x + i) < SSD1306_WIDTH; i++) {
        s_ui.frame_buffer[base_index + i] = icon_data[i];
    }
}

/**
 * @brief Get character glyph from font
 * @param c Character (ASCII 32-127)
 * @return Pointer to glyph or NULL if character not supported
 */
static const uint8_t* get_char_glyph(uint8_t c) {
    // ASCII 32-127
    if (c >= 32 && c <= 127) {
        return font_6x8[c - 32];
    }
    // Unknown character - return space
    return font_6x8[0];
}

/**
 * @brief Render character on display
 * @param x X coordinate (0-127)
 * @param y Y coordinate (0-63, must be multiple of 8 for proper rendering)
 * @param c Character to render
 */
static void render_char(uint8_t x, uint8_t y, uint8_t c) {
    if (x >= SSD1306_WIDTH || y >= SSD1306_HEIGHT) {
        return; // Выход за границы
    }
    
    // Получаем глиф символа
    const uint8_t *glyph = get_char_glyph(c);
    if (glyph == NULL) {
        return;
    }
    
    // Выравниваем Y на границу страницы (8 пикселей)
    uint8_t page = y / 8;
    if (page >= SSD1306_PAGES) {
        return;
    }
    
    // Устанавливаем курсор: колонка x, страница page
    esp_err_t err = ssd1306_write_command(SSD1306_CMD_COLUMN_ADDR);
    if (err != ESP_OK) return;
    err = ssd1306_write_command(x);
    if (err != ESP_OK) return;
    err = ssd1306_write_command(x + FONT_WIDTH - 1);
    if (err != ESP_OK) return;
    
    err = ssd1306_write_command(SSD1306_CMD_PAGE_ADDR);
    if (err != ESP_OK) return;
    err = ssd1306_write_command(page);
    if (err != ESP_OK) return;
    err = ssd1306_write_command(page);
    if (err != ESP_OK) return;
    
    // Отправляем данные глифа на дисплей
    // Глиф имеет размер 6 байт (ширина) x 8 бит (высота = 1 страница)
    err = ssd1306_write_data(glyph, FONT_WIDTH);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to write char data: %s", esp_err_to_name(err));
    }
}

/**
 * @brief Render string on display
 * @param x Start X coordinate
 * @param y Start Y coordinate
 * @param str String to render (ASCII only)
 */
static void render_string(uint8_t x, uint8_t y, const char *str) {
    if (str == NULL) return;
    
    uint8_t pos_x = x;
    const char *p = str;
    
    // Render ASCII characters only
    while (*p != '\0' && pos_x < SSD1306_WIDTH - FONT_WIDTH) {
        uint8_t c = (uint8_t)*p;
        render_char(pos_x, y, c);
        pos_x += FONT_WIDTH;
        p++;
    }
}

/**
 * @brief Render string on line
 * @param line_num Line number (0-7, each line = 8 pixels)
 * @param str String to render
 */
__attribute__((unused)) static void render_line(uint8_t line_num, const char *str) {
    if (line_num >= SSD1306_PAGES) {
        return;
    }
    render_string(0, line_num * 8, str);
}

/**
 * @brief Render WiFi icon with signal strength bars (like on phone)
 * @param x X coordinate (0-127)
 * @param y Y coordinate (0-63, must be multiple of 8)
 * @param rssi RSSI value in dBm (-100 to 0, or -100 if not connected)
 * 
 * Иконка WiFi: 4 полоски разной длины, расположенные по дуге (как на телефоне)
 * - 0 полосок: нет подключения или RSSI < -80 (отображается пустая иконка)
 * - 1 полоска: -80 <= RSSI < -70
 * - 2 полоски: -70 <= RSSI < -60
 * - 3 полоски: -60 <= RSSI < -50
 * - 4 полоски: RSSI >= -50
 * 
 * Дизайн: полоски расположены по дуге, самая короткая сверху, самая длинная снизу
 * Даже при отсутствии подключения отображается пустая иконка WiFi
 */
__attribute__((unused)) static void render_wifi_icon(uint8_t x, uint8_t y, int8_t rssi) {
    if (x >= SSD1306_WIDTH - 8 || y >= SSD1306_HEIGHT) {
        return;
    }
    
    // Определяем количество полосок на основе RSSI
    int bars = 0;
    bool is_connected = (rssi > -100);  // RSSI -100 означает отсутствие подключения
    
    if (is_connected) {
        if (rssi >= -50) {
            bars = 4;  // Отличный сигнал
        } else if (rssi >= -60) {
            bars = 3;  // Хороший сигнал
        } else if (rssi >= -70) {
            bars = 2;  // Средний сигнал
        } else if (rssi >= -80) {
            bars = 1;  // Слабый сигнал
        } else {
            bars = 0;  // Очень слабый сигнал, но подключение есть
        }
    } else {
        bars = 0;  // Нет подключения - отображаем пустую иконку
    }
    
    // Выравниваем Y на границу страницы
    uint8_t page = y / 8;
    if (page >= SSD1306_PAGES) {
        return;
    }
    
    // Создаем растровое изображение иконки WiFi (8x8 пикселей)
    // Иконка: 4 полоски, расположенные по дуге (как на телефоне)
    // Полоски идут от центра вверх и вниз
    // Каждый байт = одна строка из 8 пикселей (8 строк всего)
    // В SSD1306 биты идут слева направо: бит 7 (MSB) = левый пиксель, бит 0 (LSB) = правый пиксель
    uint8_t icon_data[8] = {0};
    
    if (is_connected && bars > 0) {
        // Рисуем полоски сигнала - более видимые, расположенные по дуге
        // Полоски идут снизу вверх, увеличиваясь в размере
        if (bars >= 1) {
            // Самая короткая полоска (верхняя) - 2 пикселя в центре
            icon_data[7] = 0x18;  // Бит 3 и 4 (0b00011000) - строка 7 (нижняя)
        }
        if (bars >= 2) {
            // Вторая полоска - 4 пикселя
            icon_data[6] = 0x3C;  // Бит 2-5 (0b00111100) - строка 6
        }
        if (bars >= 3) {
            // Третья полоска - 6 пикселей
            icon_data[5] = 0x7E;  // Бит 1-6 (0b01111110) - строка 5
        }
        if (bars >= 4) {
            // Самая длинная полоска (нижняя) - 8 пикселей
            icon_data[4] = 0xFF;  // Все биты (0b11111111) - строка 4
        }
        // Верхние строки (0-3) остаются пустыми для визуального эффекта дуги
    } else {
        // Если нет подключения, рисуем крестик для индикации отсутствия подключения
        // Крестик: диагональные линии через всю иконку (X)
        icon_data[0] = 0x81;  // Верхние углы (0b10000001)
        icon_data[1] = 0x42;  // (0b01000010)
        icon_data[2] = 0x24;  // (0b00100100)
        icon_data[3] = 0x18;  // Центр (0b00011000)
        icon_data[4] = 0x18;  // Центр (0b00011000)
        icon_data[5] = 0x24;  // (0b00100100)
        icon_data[6] = 0x42;  // (0b01000010)
        icon_data[7] = 0x81;  // Нижние углы (0b10000001)
    }
    
    // Устанавливаем область отрисовки: 8 колонок x 1 страница
    // Используем тот же подход, что и в render_char
    esp_err_t err = ssd1306_write_command(SSD1306_CMD_COLUMN_ADDR);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set column addr for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    err = ssd1306_write_command(x);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set column start for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    err = ssd1306_write_command(x + 7);  // 8 колонок (0-7)
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set column end for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    
    err = ssd1306_write_command(SSD1306_CMD_PAGE_ADDR);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set page addr for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    err = ssd1306_write_command(page);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set page start for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    err = ssd1306_write_command(page);  // 1 страница
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Failed to set page end for WiFi icon: %s", esp_err_to_name(err));
        return;
    }
    
    // Отправляем данные иконки (8 байт для 8 строк)
    err = ssd1306_write_data(icon_data, 8);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write WiFi icon data: %s (x=%d, y=%d, page=%d)", 
                 esp_err_to_name(err), x, y, page);
    } else {
        ESP_LOGI(TAG, "WiFi icon rendered: x=%d, y=%d, page=%d, rssi=%d, bars=%d, connected=%d, data=[%02X %02X %02X %02X %02X %02X %02X %02X]", 
                 x, y, page, rssi, bars, is_connected,
                 icon_data[0], icon_data[1], icon_data[2], icon_data[3],
                 icon_data[4], icon_data[5], icon_data[6], icon_data[7]);
    }
}

/**
 * @brief Отрисовка экрана BOOT
 */
static void render_boot_screen(void) {
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Если активны шаги инициализации, показываем их
    if (s_ui.init_steps_active) {
        // Определяем заголовок в зависимости от типа узла
        const char *header = "pH NODE INIT";
        switch (s_ui.node_type) {
            case OLED_UI_NODE_TYPE_PH:
                header = "pH NODE INIT";
                break;
            case OLED_UI_NODE_TYPE_EC:
                header = "EC NODE INIT";
                break;
            case OLED_UI_NODE_TYPE_CLIMATE:
                header = "CLIMATE INIT";
                break;
            case OLED_UI_NODE_TYPE_PUMP:
                header = "PUMP NODE INIT";
                break;
            default:
                header = "NODE INIT";
                break;
        }
        
        frame_buffer_draw_line(0, header);
        
        // Строка 1: "Step X/8"
        char step_line[22];
        snprintf(step_line, sizeof(step_line), "Step %d/8", s_ui.current_step_num);
        frame_buffer_draw_line(1, step_line);
        
        // Строка 2: Текст шага
        frame_buffer_draw_line(2, s_ui.current_step_text);
        
        // Строка 3: Анимация точек
        char dots_line[22] = "";
        if (s_ui.init_animation_active) {
            // Формируем строку с точками
            for (int i = 0; i < s_ui.init_dot_count && i < 3; i++) {
                dots_line[i] = '.';
            }
            dots_line[s_ui.init_dot_count] = '\0';
        }
        frame_buffer_draw_line(3, dots_line);
    } else {
        // Стандартный экран загрузки
        frame_buffer_draw_line(0, "Hydro 2.0");
        frame_buffer_draw_line(1, "Booting...");
        
        if (s_ui.model.connections.wifi_connected) {
            frame_buffer_draw_line(2, "WiFi: OK");
        } else {
            frame_buffer_draw_line(2, "WiFi: Connecting");
        }
        
        if (s_ui.model.connections.mqtt_connected) {
            frame_buffer_draw_line(3, "MQTT: OK");
        } else {
            frame_buffer_draw_line(3, "MQTT: Connecting");
        }
    }
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to update display: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
}

/**
 * @brief Отрисовка строки в буфере кадров
 * @param line_num Номер строки (0-7, каждая строка = 8 пикселей)
 * @param str Строка для отрисовки
 */
static void frame_buffer_draw_line(uint8_t line_num, const char *str) {
    if (line_num >= SSD1306_PAGES || str == NULL) {
        return;
    }
    
    uint8_t y = line_num * 8;
    uint8_t x = 0;
    const char *p = str;
    
    while (*p != '\0' && x < SSD1306_WIDTH - FONT_WIDTH) {
        frame_buffer_draw_char(x, y, (uint8_t)*p);
        x += FONT_WIDTH;
        p++;
    }
}

/**
 * @brief Отрисовка строки в буфере кадров с указанной позицией X
 * @param x Начальная X координата
 * @param y Y координата (должна быть кратна 8)
 * @param str Строка для отрисовки
 */
static void frame_buffer_draw_string(uint8_t x, uint8_t y, const char *str) {
    if (str == NULL) {
        return;
    }
    
    uint8_t pos_x = x;
    const char *p = str;
    
    while (*p != '\0' && pos_x < SSD1306_WIDTH - FONT_WIDTH) {
        frame_buffer_draw_char(pos_x, y, (uint8_t)*p);
        pos_x += FONT_WIDTH;
        p++;
    }
}

/**
 * @brief Отрисовка экрана WIFI_SETUP
 */
static void render_wifi_setup_screen(void) {
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Отрисовываем в буфер кадров
    frame_buffer_draw_line(0, "WiFi Setup");
    frame_buffer_draw_line(1, "Connect to:");
    
    // Используем zone_name из модели, если доступен, иначе используем node_uid (который содержит SSID)
    const char *ap_ssid = s_ui.model.zone_name[0] != '\0' ? s_ui.model.zone_name : 
                          (s_ui.node_uid[0] != '\0' ? s_ui.node_uid : "PH_SETUP_XXXX");
    
    ESP_LOGI(TAG, "Rendering WiFi setup screen with SSID: %s (zone_name='%s', node_uid='%s')", 
             ap_ssid, s_ui.model.zone_name, s_ui.node_uid);
    
    // Обрезаем SSID если слишком длинный для отображения (максимум 21 символ на строку)
    char display_ssid[22];
    strncpy(display_ssid, ap_ssid, sizeof(display_ssid) - 1);
    display_ssid[sizeof(display_ssid) - 1] = '\0';
    
    frame_buffer_draw_line(0, "WiFi Setup");
    frame_buffer_draw_line(1, "Connect to:");
    frame_buffer_draw_line(2, display_ssid);
    frame_buffer_draw_line(3, "Use app to");
    frame_buffer_draw_line(4, "configure");
    
    ESP_LOGI(TAG, "Frame buffer prepared, sending to display...");
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to update display: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "WiFi setup screen rendered and sent to display successfully");
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
}

/**
 * @brief Отрисовка экрана NORMAL (основной)
 */
static void render_normal_screen(void) {
    ESP_LOGD(TAG, "render_normal_screen called");
    
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Верхняя строка: иконка WiFi, статус MQTT, UID
    int8_t wifi_rssi = s_ui.model.connections.wifi_rssi;
    if (!s_ui.model.connections.wifi_connected) {
        wifi_rssi = -100;  // Нет подключения
    }
    
    // Отображаем иконку WiFi в буфере
    frame_buffer_draw_wifi_icon(0, 0, wifi_rssi);
    
    // Статус MQTT: "OK" или "ERR"
    const char *mqtt_status = "ERR";
    if (s_ui.model.connections.mqtt_connected) {
        mqtt_status = "OK";
        
        // Проверяем активность мигания (мигание длится 200 мс)
        uint64_t now_ms = esp_timer_get_time() / 1000;
        bool tx_blink = s_ui.mqtt_tx_active && (now_ms - s_ui.mqtt_tx_timestamp) < 200;
        bool rx_blink = s_ui.mqtt_rx_active && (now_ms - s_ui.mqtt_rx_timestamp) < 200;
        
        // Сбрасываем флаги после мигания
        if (!tx_blink) {
            s_ui.mqtt_tx_active = false;
        }
        if (!rx_blink) {
            s_ui.mqtt_rx_active = false;
        }
    }
    
    // Отображаем статус MQTT и UID
    char status_line[22];
    char uid_display[12];
    strncpy(uid_display, s_ui.node_uid, sizeof(uid_display) - 1);
    uid_display[sizeof(uid_display) - 1] = '\0';
    
    snprintf(status_line, sizeof(status_line), "M:%s %s", mqtt_status, uid_display);
    frame_buffer_draw_string(10, 0, status_line);  // После иконки WiFi 8px + 2px отступ
    
    // Основной блок в зависимости от типа узла и текущего экрана
    if (s_ui.current_screen == 0) {
        // Основной экран
        switch (s_ui.node_type) {
            case OLED_UI_NODE_TYPE_PH: {
                char line[22];
                // Отображаем pH значение с индикацией stub значений и ошибок
                if (s_ui.model.sensor_status.using_stub || isnan(s_ui.model.ph_value) || 
                    s_ui.model.ph_value == 0.0f || s_ui.model.sensor_status.has_error) {
                    snprintf(line, sizeof(line), "pH: --.--");
                } else {
                    snprintf(line, sizeof(line), "pH: %.2f", s_ui.model.ph_value);
                }
                frame_buffer_draw_line(2, line);
                
                // Статус I2C подключения и ошибки
                if (s_ui.model.sensor_status.has_error) {
                    // Показываем ошибку или статус I2C
                    if (s_ui.model.sensor_status.error_msg[0] != '\0') {
                        char error_line[22];
                        strncpy(error_line, s_ui.model.sensor_status.error_msg, sizeof(error_line) - 1);
                        error_line[sizeof(error_line) - 1] = '\0';
                        frame_buffer_draw_line(3, error_line);
                    } else if (!s_ui.model.sensor_status.i2c_connected) {
                        frame_buffer_draw_line(3, "I2C: Disconnected");
                    } else {
                        frame_buffer_draw_line(3, "Sensor error");
                    }
                } else {
                    // Нормальный режим - показываем статус I2C и температуру
                    if (!isnan(s_ui.model.temperature_water)) {
                        snprintf(line, sizeof(line), "Temp: %.1fC", s_ui.model.temperature_water);
                        frame_buffer_draw_line(3, line);
                    } else {
                        frame_buffer_draw_line(3, "I2C: OK");
                    }
                }
                break;
            }
            case OLED_UI_NODE_TYPE_EC: {
                char line[22];
                snprintf(line, sizeof(line), "EC: %.2f", s_ui.model.ec_value);
                frame_buffer_draw_line(2, line);
                snprintf(line, sizeof(line), "Temp: %.1fC", s_ui.model.temperature_water);
                frame_buffer_draw_line(3, line);
                break;
            }
            case OLED_UI_NODE_TYPE_CLIMATE: {
                char line[22];
                // Строка 2: Температура и влажность - показываем прочерки при ошибках (как в ph_node)
                if (!isnan(s_ui.model.temperature_air) && isfinite(s_ui.model.temperature_air) &&
                    !isnan(s_ui.model.humidity) && isfinite(s_ui.model.humidity) &&
                    s_ui.model.temperature_air >= -40.0f && s_ui.model.temperature_air <= 125.0f &&
                    s_ui.model.humidity >= 0.0f && s_ui.model.humidity <= 100.0f) {
                    snprintf(line, sizeof(line), "T:%.1fC H:%.0f%%", 
                            s_ui.model.temperature_air, s_ui.model.humidity);
                } else {
                    // Показываем прочерки при ошибках или невалидных значениях
                    strncpy(line, "T:--.-C H:--%", sizeof(line) - 1);
                    line[sizeof(line) - 1] = '\0';
                }
                frame_buffer_draw_line(2, line);
                
                // Строка 3: CO2 или статус I2C
                if (!isnan(s_ui.model.co2) && isfinite(s_ui.model.co2) && s_ui.model.co2 >= 0.0f) {
                    snprintf(line, sizeof(line), "CO2: %d ppm", (int)s_ui.model.co2);
                } else {
                    // Если CO2 не доступен, показываем статус I2C
                    if (s_ui.model.sensor_status.i2c_connected) {
                        strncpy(line, "I2C: OK", sizeof(line) - 1);
                    } else {
                        strncpy(line, "I2C: ERR", sizeof(line) - 1);
                    }
                    line[sizeof(line) - 1] = '\0';
                }
                frame_buffer_draw_line(3, line);
                break;
            }
            case OLED_UI_NODE_TYPE_LIGHTING: {
                char line[22];
                // Строка 2: Освещенность - показываем прочерки при ошибках (как в ph_node)
                if (!isnan(s_ui.model.lux_value) && isfinite(s_ui.model.lux_value) && s_ui.model.lux_value >= 0.0f) {
                    snprintf(line, sizeof(line), "Lux: %.0f", s_ui.model.lux_value);
                } else {
                    // Показываем прочерки при ошибках или невалидных значениях
                    strncpy(line, "Lux: --", sizeof(line) - 1);
                    line[sizeof(line) - 1] = '\0';
                }
                frame_buffer_draw_line(2, line);
                
                // Строка 3: Статус I2C или ошибка
                if (s_ui.model.sensor_status.i2c_connected) {
                    if (s_ui.model.sensor_status.has_error && s_ui.model.sensor_status.error_msg[0] != '\0') {
                        // Показываем сообщение об ошибке, если есть
                        strncpy(line, s_ui.model.sensor_status.error_msg, sizeof(line) - 1);
                        line[sizeof(line) - 1] = '\0';
                    } else {
                        // Датчик подключен и работает
                        strncpy(line, "I2C: OK", sizeof(line) - 1);
                        line[sizeof(line) - 1] = '\0';
                    }
                } else {
                    strncpy(line, "I2C: ERR", sizeof(line) - 1);
                    line[sizeof(line) - 1] = '\0';
                }
                frame_buffer_draw_line(3, line);
                break;
            }
            default:
                frame_buffer_draw_line(2, "Node active");
                break;
        }
    } else if (s_ui.current_screen == 1) {
        // Экран каналов
        frame_buffer_draw_line(1, "Channels:");
        for (size_t i = 0; i < s_ui.model.channel_count && i < 5; i++) {
            char line[22];
            snprintf(line, sizeof(line), "%s: %.2f",
                    s_ui.model.channels[i].name,
                    s_ui.model.channels[i].value);
            frame_buffer_draw_line(2 + i, line);
        }
    } else if (s_ui.current_screen == 2) {
        // Экран зоны
        frame_buffer_draw_line(1, "Zone:");
        frame_buffer_draw_line(2, s_ui.model.zone_name);
        frame_buffer_draw_line(3, "Recipe:");
        frame_buffer_draw_line(4, s_ui.model.recipe_name);
    }
    
    // Нижняя строка: состояние
    if (s_ui.model.alert) {
        frame_buffer_draw_line(7, "ALERT");
    } else if (s_ui.model.paused) {
        frame_buffer_draw_line(7, "PAUSED");
    } else {
        frame_buffer_draw_line(7, "OK");
    }
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to update display: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
}

/**
 * @brief Отрисовка экрана ALERT
 */
static void render_alert_screen(void) {
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Отрисовываем в буфер кадров
    frame_buffer_draw_line(2, "ALERT");
    frame_buffer_draw_line(3, s_ui.model.alert_message);
    frame_buffer_draw_line(5, "See app");
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to update display: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
}

/**
 * @brief Отрисовка экрана CALIBRATION
 */
static void render_calibration_screen(void) {
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Отрисовываем в буфер кадров
    frame_buffer_draw_line(1, "Calibration");
    frame_buffer_draw_line(2, "Follow");
    frame_buffer_draw_line(3, "instructions");
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to update display: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
}

/**
 * @brief Отрисовка экрана SERVICE
 */
static void render_service_screen(void) {
    // Захватываем mutex для защиты от одновременного доступа
    if (s_ui.render_mutex != NULL && xSemaphoreTake(s_ui.render_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take render mutex, skipping render");
        return;
    }
    
    // Очищаем буфер кадров
    frame_buffer_clear();
    
    // Отрисовываем в буфер кадров
    frame_buffer_draw_line(0, "Service Menu");
    frame_buffer_draw_line(2, "Node:");
    frame_buffer_draw_line(3, s_ui.node_uid);
    
    // Отправляем весь буфер на дисплей за один раз
    esp_err_t err = ssd1306_update_display();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to update display: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (s_ui.render_mutex != NULL) {
        xSemaphoreGive(s_ui.render_mutex);
    }
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
    ESP_LOGI(TAG, "=== OLED UI Init Start ===");
    ESP_LOGI(TAG, "node_type=%d, node_uid=%s", node_type, node_uid ? node_uid : "NULL");
    
    if (s_ui.initialized) {
        ESP_LOGW(TAG, "OLED UI already initialized");
        return ESP_OK;
    }
    
    ESP_LOGI(TAG, "Checking I²C bus initialization...");
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    ESP_LOGI(TAG, "I²C bus is initialized");
    
    // Создание mutex для защиты операций отрисовки
    if (s_ui.render_mutex == NULL) {
        s_ui.render_mutex = xSemaphoreCreateMutex();
        if (s_ui.render_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create render mutex");
            return ESP_ERR_NO_MEM;
        }
        ESP_LOGI(TAG, "Render mutex created");
    }
    
    // Инициализация флагов MQTT активности
    s_ui.mqtt_tx_active = false;
    s_ui.mqtt_rx_active = false;
    s_ui.mqtt_tx_timestamp = 0;
    s_ui.mqtt_rx_timestamp = 0;
    
    // Сохранение параметров
    s_ui.node_type = node_type;
    if (node_uid != NULL) {
        strncpy(s_ui.node_uid, node_uid, sizeof(s_ui.node_uid) - 1);
        s_ui.node_uid[sizeof(s_ui.node_uid) - 1] = '\0';
    } else {
        s_ui.node_uid[0] = '\0';
    }
    
    // Конфигурация
    if (config != NULL) {
        memcpy(&s_ui.config, config, sizeof(oled_ui_config_t));
        ESP_LOGI(TAG, "Using provided config: addr=0x%02X, interval=%dms, task=%s", 
                 config->i2c_address, config->update_interval_ms, 
                 config->enable_task ? "yes" : "no");
    } else {
        s_ui.config.i2c_address = SSD1306_I2C_ADDR_DEFAULT;
        s_ui.config.update_interval_ms = 1500;  // Увеличено с 500 до 1500 мс для плавного обновления
        s_ui.config.enable_task = true;
        ESP_LOGI(TAG, "Using default config: addr=0x%02X, interval=%dms", 
                 s_ui.config.i2c_address, s_ui.config.update_interval_ms);
    }
    
    s_ui.i2c_address = s_ui.config.i2c_address;
    s_ui.state = OLED_UI_STATE_BOOT;
    s_ui.current_screen = 0;
    
    ESP_LOGI(TAG, "Starting SSD1306 initialization...");
    // Инициализация дисплея
    esp_err_t err = ssd1306_init_display();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SSD1306: %s", esp_err_to_name(err));
        return err;
    }
    
    // Инициализация модели
    memset(&s_ui.model, 0, sizeof(oled_ui_model_t));
    
    s_ui.initialized = true;
    ESP_LOGI(TAG, "OLED UI initialized successfully (node_type=%d, addr=0x%02X, uid=%s)", 
             node_type, s_ui.i2c_address, s_ui.node_uid);
    
    // Запуск задачи обновления
    if (s_ui.config.enable_task) {
        ESP_LOGI(TAG, "Starting OLED update task...");
        err = oled_ui_start_task();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to start update task: %s", esp_err_to_name(err));
        } else {
            ESP_LOGI(TAG, "OLED update task started");
        }
    } else {
        ESP_LOGI(TAG, "OLED update task disabled in config");
    }
    
    ESP_LOGI(TAG, "=== OLED UI Init Complete ===");
    return ESP_OK;
}

esp_err_t oled_ui_deinit(void) {
    if (!s_ui.initialized) {
        return ESP_OK;
    }
    
    // Остановка задачи
    oled_ui_stop_task();
    
    // Удаление mutex
    if (s_ui.render_mutex != NULL) {
        vSemaphoreDelete(s_ui.render_mutex);
        s_ui.render_mutex = NULL;
        ESP_LOGI(TAG, "Render mutex deleted");
    }
    
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
    
    // Мержим значения вместо полной замены, чтобы сохранить необновленные поля
    // Обновляем только те поля, которые были явно установлены (не равны 0 или не пустые)
    
    // Соединения - всегда обновляем
    s_ui.model.connections = model->connections;
    
    // Значения сенсоров - обновляем только если они валидны (не NaN, не бесконечность)
    if (!isnan(model->ph_value) && isfinite(model->ph_value)) {
        s_ui.model.ph_value = model->ph_value;
    }
    if (!isnan(model->ec_value) && isfinite(model->ec_value)) {
        s_ui.model.ec_value = model->ec_value;
    }
    if (!isnan(model->temperature_air) && isfinite(model->temperature_air)) {
        s_ui.model.temperature_air = model->temperature_air;
    }
    if (!isnan(model->temperature_water) && isfinite(model->temperature_water)) {
        s_ui.model.temperature_water = model->temperature_water;
    }
    if (!isnan(model->humidity) && isfinite(model->humidity)) {
        s_ui.model.humidity = model->humidity;
    }
    if (!isnan(model->co2) && isfinite(model->co2)) {
        s_ui.model.co2 = model->co2;
    }
    if (!isnan(model->lux_value) && isfinite(model->lux_value)) {
        s_ui.model.lux_value = model->lux_value;
    }
    
    // Статус датчиков - всегда обновляем
    s_ui.model.sensor_status = model->sensor_status;
    
    // Статус узла - всегда обновляем
    s_ui.model.alert = model->alert;
    s_ui.model.paused = model->paused;
    if (model->alert_message[0] != '\0') {
        strncpy(s_ui.model.alert_message, model->alert_message, sizeof(s_ui.model.alert_message) - 1);
        s_ui.model.alert_message[sizeof(s_ui.model.alert_message) - 1] = '\0';
    }
    
    // Информация о зоне/рецепте - обновляем только если не пустые
    if (model->zone_name[0] != '\0') {
        strncpy(s_ui.model.zone_name, model->zone_name, sizeof(s_ui.model.zone_name) - 1);
        s_ui.model.zone_name[sizeof(s_ui.model.zone_name) - 1] = '\0';
    }
    if (model->recipe_name[0] != '\0') {
        strncpy(s_ui.model.recipe_name, model->recipe_name, sizeof(s_ui.model.recipe_name) - 1);
        s_ui.model.recipe_name[sizeof(s_ui.model.recipe_name) - 1] = '\0';
    }
    
    // Каналы - обновляем только если есть каналы
    if (model->channel_count > 0 && model->channel_count <= 8) {
        s_ui.model.channel_count = model->channel_count;
        for (size_t i = 0; i < model->channel_count; i++) {
            s_ui.model.channels[i] = model->channels[i];
        }
    }
    
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

void oled_ui_notify_mqtt_tx(void) {
    if (!s_ui.initialized) {
        return;
    }
    s_ui.mqtt_tx_active = true;
    s_ui.mqtt_tx_timestamp = esp_timer_get_time() / 1000;  // Время в миллисекундах
}

void oled_ui_notify_mqtt_rx(void) {
    if (!s_ui.initialized) {
        return;
    }
    s_ui.mqtt_rx_active = true;
    s_ui.mqtt_rx_timestamp = esp_timer_get_time() / 1000;  // Время в миллисекундах
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

bool oled_ui_is_initialized(void) {
    return s_ui.initialized;
}

// Задача анимации точек для шагов инициализации
#define INIT_STEP_ANIMATION_INTERVAL_MS 500

static void init_step_animation_task(void *arg) {
    (void)arg;
    s_ui.init_dot_count = 0;

    while (s_ui.init_animation_active && s_ui.init_steps_active) {
        // Обновляем количество точек (0, 1, 2, 3 -> "", ".", "..", "...")
        s_ui.init_dot_count = (s_ui.init_dot_count + 1) % 4;

        // Обновляем отображение через oled_ui_refresh (он сам вызовет render_boot_screen с защитой mutex)
        if (s_ui.initialized && s_ui.state == OLED_UI_STATE_BOOT) {
            oled_ui_refresh();
        }

        vTaskDelay(pdMS_TO_TICKS(INIT_STEP_ANIMATION_INTERVAL_MS));
    }

    s_ui.init_animation_task = NULL;
    s_ui.init_dot_count = 0;
    vTaskDelete(NULL);
}

esp_err_t oled_ui_show_init_step(int step_num, const char *step_text) {
    if (!s_ui.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    // Устанавливаем состояние BOOT, если еще не установлено
    if (s_ui.state != OLED_UI_STATE_BOOT) {
        s_ui.state = OLED_UI_STATE_BOOT;
    }

    // Активируем режим шагов инициализации
    s_ui.init_steps_active = true;
    s_ui.current_step_num = step_num;
    
    if (step_text) {
        strncpy(s_ui.current_step_text, step_text, sizeof(s_ui.current_step_text) - 1);
        s_ui.current_step_text[sizeof(s_ui.current_step_text) - 1] = '\0';
    } else {
        s_ui.current_step_text[0] = '\0';
    }

    // Запускаем анимацию, если еще не запущена
    if (!s_ui.init_animation_active) {
        s_ui.init_animation_active = true;
        if (xTaskCreate(init_step_animation_task, "init_step_anim", 2048, NULL, 4, 
                       &s_ui.init_animation_task) != pdPASS) {
            ESP_LOGE(TAG, "Failed to create init step animation task");
            s_ui.init_animation_task = NULL;
            s_ui.init_animation_active = false;
            return ESP_FAIL;
        }
    }

    // Обновляем экран (oled_ui_refresh сам вызовет render_boot_screen с защитой mutex)
    oled_ui_refresh();

    ESP_LOGI(TAG, "Init step %d: %s", step_num, step_text ? step_text : "");
    return ESP_OK;
}

esp_err_t oled_ui_stop_init_steps(void) {
    if (!s_ui.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    // Останавливаем анимацию
    s_ui.init_animation_active = false;
    int wait_count = 0;
    while (s_ui.init_animation_task != NULL && wait_count < 50) {
        vTaskDelay(pdMS_TO_TICKS(20));
        wait_count++;
    }

    if (s_ui.init_animation_task != NULL) {
        ESP_LOGW(TAG, "Init animation task still exists after wait");
    }

    // Деактивируем режим шагов
    s_ui.init_steps_active = false;
    s_ui.current_step_num = 0;
    s_ui.current_step_text[0] = '\0';

    // Обновляем экран (вернется к стандартному BOOT экрану, oled_ui_refresh сам вызовет render_boot_screen с защитой mutex)
    oled_ui_refresh();

    ESP_LOGI(TAG, "Init steps stopped");
    return ESP_OK;
}

