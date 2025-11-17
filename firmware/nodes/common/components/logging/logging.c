/**
 * @file logging.c
 * @brief Реализация системы логирования
 * 
 * Компонент предоставляет расширенную систему логирования:
 * - Уровни логирования
 * - Отправка логов через MQTT
 * - Ротация логов в NVS
 * - Форматирование с временными метками
 * 
 * Стандарты кодирования:
 * - Именование функций: logging_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "logging.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_timer.h"
#include <string.h>
#include <stdio.h>
#include <stdarg.h>

static const char *TAG = "logging";
static const char *NVS_NAMESPACE = "logging";
static const char *NVS_KEY_LOGS = "logs";
static const char *NVS_KEY_INDEX = "index";

// Внутренние структуры
static struct {
    bool initialized;
    logging_config_t config;
    logging_mqtt_callback_t mqtt_callback;
    void *mqtt_user_ctx;
    nvs_handle_t nvs_handle;
    size_t nvs_log_index;
    char *nvs_buffer;
} s_logging = {0};

// Внутренние функции
static const char *log_level_to_string(log_level_t level);
static esp_err_t logging_save_to_nvs(log_level_t level, const char *tag, const char *message);
static void logging_send_to_mqtt(log_level_t level, const char *tag, const char *message);

/**
 * @brief Преобразование уровня логирования в строку
 */
static const char *log_level_to_string(log_level_t level) {
    switch (level) {
        case LOG_LEVEL_ERROR: return "ERROR";
        case LOG_LEVEL_WARN:  return "WARN";
        case LOG_LEVEL_INFO:  return "INFO";
        case LOG_LEVEL_DEBUG: return "DEBUG";
        case LOG_LEVEL_VERBOSE: return "VERBOSE";
        default: return "UNKNOWN";
    }
}

/**
 * @brief Сохранение лога в NVS
 */
static esp_err_t logging_save_to_nvs(log_level_t level, const char *tag, const char *message) {
    if (!s_logging.initialized || !s_logging.config.enable_nvs) {
        return ESP_OK;
    }
    
    if (s_logging.nvs_handle == 0) {
        return ESP_ERR_INVALID_STATE;
    }
    
    // Формирование строки лога с временной меткой
    int64_t timestamp = esp_timer_get_time() / 1000;  // В миллисекундах
    char log_entry[256];
    int len = snprintf(log_entry, sizeof(log_entry), "[%lld] %s [%s] %s\n",
                      timestamp, log_level_to_string(level), tag, message);
    
    if (len < 0 || len >= sizeof(log_entry)) {
        ESP_LOGW(TAG, "Log entry too long, truncating");
        len = sizeof(log_entry) - 1;
    }
    
    // Простая ротация: записываем в буфер по кругу
    size_t entry_len = strlen(log_entry);
    if (entry_len > s_logging.config.nvs_buffer_size) {
        // Лог слишком большой, пропускаем
        return ESP_ERR_INVALID_SIZE;
    }
    
    // Проверка, поместится ли лог в буфер
    size_t current_pos = s_logging.nvs_log_index;
    size_t remaining = s_logging.config.nvs_buffer_size - current_pos;
    
    if (remaining < entry_len) {
        // Не помещается, начинаем с начала (ротация)
        current_pos = 0;
        s_logging.nvs_log_index = 0;
    }
    
    // Копирование лога в буфер
    memcpy(&s_logging.nvs_buffer[current_pos], log_entry, entry_len);
    s_logging.nvs_log_index = current_pos + entry_len;
    
    // Сохранение в NVS
    esp_err_t err = nvs_set_blob(s_logging.nvs_handle, NVS_KEY_LOGS, s_logging.nvs_buffer, 
                                 s_logging.config.nvs_buffer_size);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save logs to NVS: %s", esp_err_to_name(err));
        return err;
    }
    
    err = nvs_set_i32(s_logging.nvs_handle, NVS_KEY_INDEX, s_logging.nvs_log_index);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to save log index to NVS");
    }
    
    err = nvs_commit(s_logging.nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to commit NVS");
    }
    
    return ESP_OK;
}

/**
 * @brief Отправка лога через MQTT
 */
static void logging_send_to_mqtt(log_level_t level, const char *tag, const char *message) {
    if (!s_logging.initialized || !s_logging.config.enable_mqtt) {
        return;
    }
    
    if (s_logging.mqtt_callback != NULL) {
        s_logging.mqtt_callback(level, tag, message, s_logging.mqtt_user_ctx);
    }
}

// Публичные функции

esp_err_t logging_init(const logging_config_t *config) {
    if (s_logging.initialized) {
        ESP_LOGW(TAG, "Logging already initialized");
        return ESP_OK;
    }
    
    // Конфигурация
    if (config != NULL) {
        memcpy(&s_logging.config, config, sizeof(logging_config_t));
    } else {
        // Значения по умолчанию
        s_logging.config.level = LOG_LEVEL_INFO;
        s_logging.config.enable_mqtt = false;
        s_logging.config.enable_nvs = true;
        s_logging.config.nvs_buffer_size = 2048;
        s_logging.config.max_log_length = 256;
    }
    
    // Инициализация NVS
    if (s_logging.config.enable_nvs) {
        esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &s_logging.nvs_handle);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to open NVS namespace: %s", esp_err_to_name(err));
            // Продолжаем без NVS
            s_logging.config.enable_nvs = false;
        } else {
            // Выделение буфера для логов
            s_logging.nvs_buffer = malloc(s_logging.config.nvs_buffer_size);
            if (s_logging.nvs_buffer == NULL) {
                ESP_LOGE(TAG, "Failed to allocate NVS buffer");
                s_logging.config.enable_nvs = false;
            } else {
                memset(s_logging.nvs_buffer, 0, s_logging.config.nvs_buffer_size);
                
                // Загрузка существующих логов
                size_t required_size = s_logging.config.nvs_buffer_size;
                err = nvs_get_blob(s_logging.nvs_handle, NVS_KEY_LOGS, s_logging.nvs_buffer, 
                                  &required_size);
                if (err == ESP_OK) {
                    // Загрузка индекса
                    int32_t index = 0;
                    nvs_get_i32(s_logging.nvs_handle, NVS_KEY_INDEX, &index);
                    s_logging.nvs_log_index = (size_t)index;
                }
            }
        }
    }
    
    s_logging.mqtt_callback = NULL;
    s_logging.mqtt_user_ctx = NULL;
    s_logging.initialized = true;
    
    ESP_LOGI(TAG, "Logging system initialized (level=%d, mqtt=%d, nvs=%d)",
            s_logging.config.level, s_logging.config.enable_mqtt, s_logging.config.enable_nvs);
    
    return ESP_OK;
}

esp_err_t logging_deinit(void) {
    if (!s_logging.initialized) {
        return ESP_OK;
    }
    
    // Закрытие NVS
    if (s_logging.nvs_handle != 0) {
        nvs_close(s_logging.nvs_handle);
        s_logging.nvs_handle = 0;
    }
    
    // Освобождение буфера
    if (s_logging.nvs_buffer != NULL) {
        free(s_logging.nvs_buffer);
        s_logging.nvs_buffer = NULL;
    }
    
    s_logging.mqtt_callback = NULL;
    s_logging.mqtt_user_ctx = NULL;
    s_logging.initialized = false;
    
    ESP_LOGI(TAG, "Logging system deinitialized");
    return ESP_OK;
}

void logging_set_level(log_level_t level) {
    if (s_logging.initialized) {
        s_logging.config.level = level;
    }
}

log_level_t logging_get_level(void) {
    if (s_logging.initialized) {
        return s_logging.config.level;
    }
    return LOG_LEVEL_INFO;
}

void logging_register_mqtt_callback(logging_mqtt_callback_t callback, void *user_ctx) {
    s_logging.mqtt_callback = callback;
    s_logging.mqtt_user_ctx = user_ctx;
}

void logging_log(log_level_t level, const char *tag, const char *format, ...) {
    if (!s_logging.initialized) {
        // Fallback на ESP_LOG
        va_list args;
        va_start(args, format);
        switch (level) {
            case LOG_LEVEL_ERROR:
                esp_log_writev(ESP_LOG_ERROR, tag, format, args);
                break;
            case LOG_LEVEL_WARN:
                esp_log_writev(ESP_LOG_WARN, tag, format, args);
                break;
            case LOG_LEVEL_INFO:
                esp_log_writev(ESP_LOG_INFO, tag, format, args);
                break;
            case LOG_LEVEL_DEBUG:
                esp_log_writev(ESP_LOG_DEBUG, tag, format, args);
                break;
            default:
                esp_log_writev(ESP_LOG_VERBOSE, tag, format, args);
                break;
        }
        va_end(args);
        return;
    }
    
    // Проверка уровня
    if (level > s_logging.config.level) {
        return;
    }
    
    // Форматирование сообщения
    char message[256];
    va_list args;
    va_start(args, format);
    int len = vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    
    if (len < 0 || len >= sizeof(message)) {
        ESP_LOGW(TAG, "Log message too long, truncating");
        len = sizeof(message) - 1;
    }
    message[len] = '\0';
    
    // Логирование через ESP_LOG
    switch (level) {
        case LOG_LEVEL_ERROR:
            ESP_LOGE(tag, "%s", message);
            break;
        case LOG_LEVEL_WARN:
            ESP_LOGW(tag, "%s", message);
            break;
        case LOG_LEVEL_INFO:
            ESP_LOGI(tag, "%s", message);
            break;
        case LOG_LEVEL_DEBUG:
            ESP_LOGD(tag, "%s", message);
            break;
        default:
            ESP_LOGV(tag, "%s", message);
            break;
    }
    
    // Сохранение в NVS
    if (s_logging.config.enable_nvs) {
        logging_save_to_nvs(level, tag, message);
    }
    
    // Отправка через MQTT
    if (s_logging.config.enable_mqtt) {
        logging_send_to_mqtt(level, tag, message);
    }
}

void logging_vlog(log_level_t level, const char *tag, const char *format, va_list args) {
    if (!s_logging.initialized) {
        // Fallback на ESP_LOG
        switch (level) {
            case LOG_LEVEL_ERROR:
                esp_log_writev(ESP_LOG_ERROR, tag, format, args);
                break;
            case LOG_LEVEL_WARN:
                esp_log_writev(ESP_LOG_WARN, tag, format, args);
                break;
            case LOG_LEVEL_INFO:
                esp_log_writev(ESP_LOG_INFO, tag, format, args);
                break;
            case LOG_LEVEL_DEBUG:
                esp_log_writev(ESP_LOG_DEBUG, tag, format, args);
                break;
            default:
                esp_log_writev(ESP_LOG_VERBOSE, tag, format, args);
                break;
        }
        return;
    }
    
    // Проверка уровня
    if (level > s_logging.config.level) {
        return;
    }
    
    // Форматирование сообщения
    char message[256];
    int len = vsnprintf(message, sizeof(message), format, args);
    
    if (len < 0 || len >= sizeof(message)) {
        ESP_LOGW(TAG, "Log message too long, truncating");
        len = sizeof(message) - 1;
    }
    message[len] = '\0';
    
    // Логирование через ESP_LOG
    switch (level) {
        case LOG_LEVEL_ERROR:
            ESP_LOGE(tag, "%s", message);
            break;
        case LOG_LEVEL_WARN:
            ESP_LOGW(tag, "%s", message);
            break;
        case LOG_LEVEL_INFO:
            ESP_LOGI(tag, "%s", message);
            break;
        case LOG_LEVEL_DEBUG:
            ESP_LOGD(tag, "%s", message);
            break;
        default:
            ESP_LOGV(tag, "%s", message);
            break;
    }
    
    // Сохранение в NVS
    if (s_logging.config.enable_nvs) {
        logging_save_to_nvs(level, tag, message);
    }
    
    // Отправка через MQTT
    if (s_logging.config.enable_mqtt) {
        logging_send_to_mqtt(level, tag, message);
    }
}

esp_err_t logging_get_nvs_logs(char *buffer, size_t buffer_size, size_t *log_count) {
    if (!s_logging.initialized || !s_logging.config.enable_nvs) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (buffer == NULL || buffer_size == 0 || log_count == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (s_logging.nvs_buffer == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    
    // Копирование логов из буфера
    size_t copy_size = (s_logging.nvs_log_index < buffer_size) ? 
                      s_logging.nvs_log_index : buffer_size - 1;
    memcpy(buffer, s_logging.nvs_buffer, copy_size);
    buffer[copy_size] = '\0';
    
    // Подсчет количества логов (приблизительно)
    *log_count = 0;
    for (size_t i = 0; i < copy_size; i++) {
        if (buffer[i] == '\n') {
            (*log_count)++;
        }
    }
    
    return ESP_OK;
}

esp_err_t logging_clear_nvs_logs(void) {
    if (!s_logging.initialized || !s_logging.config.enable_nvs) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (s_logging.nvs_buffer != NULL) {
        memset(s_logging.nvs_buffer, 0, s_logging.config.nvs_buffer_size);
        s_logging.nvs_log_index = 0;
        
        // Сохранение в NVS
        esp_err_t err = nvs_set_blob(s_logging.nvs_handle, NVS_KEY_LOGS, s_logging.nvs_buffer, 
                                     s_logging.config.nvs_buffer_size);
        if (err != ESP_OK) {
            return err;
        }
        
        err = nvs_set_i32(s_logging.nvs_handle, NVS_KEY_INDEX, 0);
        if (err != ESP_OK) {
            return err;
        }
        
        err = nvs_commit(s_logging.nvs_handle);
        return err;
    }
    
    return ESP_OK;
}

