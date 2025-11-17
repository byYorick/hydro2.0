/**
 * @file logging.h
 * @brief Система логирования для узлов ESP32
 * 
 * Компонент предоставляет расширенную систему логирования:
 * - Уровни логирования (ERROR, WARN, INFO, DEBUG)
 * - Отправка логов через MQTT (опционально)
 * - Ротация логов в NVS (ограниченный буфер)
 * - Форматирование с временными метками
 * - Интеграция с ESP_LOG для единообразного логирования
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 */

#ifndef LOGGING_H
#define LOGGING_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Уровни логирования
 */
typedef enum {
    LOG_LEVEL_ERROR = 0,
    LOG_LEVEL_WARN,
    LOG_LEVEL_INFO,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_VERBOSE
} log_level_t;

/**
 * @brief Конфигурация логирования
 */
typedef struct {
    log_level_t level;              ///< Минимальный уровень логирования
    bool enable_mqtt;              ///< Отправлять логи через MQTT
    bool enable_nvs;               ///< Сохранять логи в NVS
    size_t nvs_buffer_size;        ///< Размер буфера в NVS (в байтах)
    size_t max_log_length;         ///< Максимальная длина одного лога
} logging_config_t;

/**
 * @brief Callback для отправки логов через MQTT
 * 
 * @param level Уровень логирования
 * @param tag Тег лога
 * @param message Сообщение лога
 * @param user_ctx Пользовательский контекст
 */
typedef void (*logging_mqtt_callback_t)(log_level_t level, const char *tag, 
                                        const char *message, void *user_ctx);

/**
 * @brief Инициализация системы логирования
 * 
 * @param config Конфигурация (может быть NULL для значений по умолчанию)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t logging_init(const logging_config_t *config);

/**
 * @brief Деинициализация системы логирования
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t logging_deinit(void);

/**
 * @brief Установка уровня логирования
 * 
 * @param level Новый уровень логирования
 */
void logging_set_level(log_level_t level);

/**
 * @brief Получение текущего уровня логирования
 * 
 * @return log_level_t Текущий уровень
 */
log_level_t logging_get_level(void);

/**
 * @brief Регистрация callback для отправки логов через MQTT
 * 
 * @param callback Callback функция
 * @param user_ctx Пользовательский контекст
 */
void logging_register_mqtt_callback(logging_mqtt_callback_t callback, void *user_ctx);

/**
 * @brief Логирование сообщения
 * 
 * @param level Уровень логирования
 * @param tag Тег лога
 * @param format Формат строки (как printf)
 * @param ... Аргументы для форматирования
 */
void logging_log(log_level_t level, const char *tag, const char *format, ...);

/**
 * @brief Логирование сообщения с va_list
 * 
 * @param level Уровень логирования
 * @param tag Тег лога
 * @param format Формат строки
 * @param args Аргументы для форматирования
 */
void logging_vlog(log_level_t level, const char *tag, const char *format, va_list args);

/**
 * @brief Макросы для удобного логирования
 */
#define LOG_ERROR(tag, format, ...) logging_log(LOG_LEVEL_ERROR, tag, format, ##__VA_ARGS__)
#define LOG_WARN(tag, format, ...)  logging_log(LOG_LEVEL_WARN, tag, format, ##__VA_ARGS__)
#define LOG_INFO(tag, format, ...)  logging_log(LOG_LEVEL_INFO, tag, format, ##__VA_ARGS__)
#define LOG_DEBUG(tag, format, ...) logging_log(LOG_LEVEL_DEBUG, tag, format, ##__VA_ARGS__)

/**
 * @brief Получение логов из NVS
 * 
 * @param buffer Буфер для сохранения логов
 * @param buffer_size Размер буфера
 * @param log_count Указатель для сохранения количества логов
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t logging_get_nvs_logs(char *buffer, size_t buffer_size, size_t *log_count);

/**
 * @brief Очистка логов в NVS
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t logging_clear_nvs_logs(void);

#ifdef __cplusplus
}
#endif

#endif // LOGGING_H

