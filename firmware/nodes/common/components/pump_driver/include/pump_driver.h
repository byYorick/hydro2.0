/**
 * @file pump_driver.h
 * @brief Общий драйвер для управления насосами через GPIO/MOSFET
 * 
 * Компонент предоставляет интерфейс для управления насосами:
 * - Инициализация каналов насосов из NodeConfig
 * - Управление насосами через GPIO/MOSFET (low-side)
 * - Поддержка NC (Normaly-Closed) и NO (Normaly-Open) реле
 * - Соблюдение safe_limits из NodeConfig (max_duration, min_off_time)
 * - Интеграция с relay_driver для управления через реле
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/HARDWARE_ARCH_FULL.md (раздел 8.2)
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md
 */

#ifndef PUMP_DRIVER_H
#define PUMP_DRIVER_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Forward declaration для ina209_config_t
// Реальная структура определена в ina209.h
#include "ina209.h"

/**
 * @brief Состояние насоса
 */
typedef enum {
    PUMP_STATE_OFF = 0,         ///< Насос выключен
    PUMP_STATE_ON = 1,          ///< Насос включен
    PUMP_STATE_COOLDOWN = 2,    ///< Насос в режиме охлаждения
    PUMP_STATE_ERROR = 3        ///< Ошибка насоса
} pump_driver_state_t;

/**
 * @brief Конфигурация канала насоса
 */
typedef struct {
    const char *channel_name;        ///< Имя канала (из NodeConfig)
    int gpio_pin;                   ///< GPIO пин для управления MOSFET
    bool use_relay;                 ///< true если управление через реле, false если напрямую через GPIO
    const char *relay_channel;      ///< Имя канала реле (если use_relay == true)
    bool fail_safe_nc;              ///< true если реле NC (normaly-closed), false если NO
    uint32_t max_duration_ms;       ///< Максимальная длительность работы (мс)
    uint32_t min_off_time_ms;       ///< Минимальное время простоя (мс)
    float ml_per_second;            ///< Производительность (мл/сек) для расчета дозы
} pump_channel_config_t;

/**
 * @brief Инициализация драйвера насосов
 * 
 * @param channels Массив конфигураций каналов насосов
 * @param channel_count Количество каналов
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_init(const pump_channel_config_t *channels, size_t channel_count);

/**
 * @brief Инициализация драйвера насосов из NodeConfig
 * 
 * Читает конфигурацию каналов из NodeConfig и инициализирует насосы
 * Также инициализирует INA209 для проверки тока (если настроен)
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_init_from_config(void);

/**
 * @brief Установить конфигурацию INA209 для проверки тока
 * 
 * @param config Конфигурация INA209 (может быть NULL, если INA209 не используется)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_set_ina209_config(const ina209_config_t *config);

/**
 * @brief Деинициализация драйвера насосов
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_deinit(void);

/**
 * @brief Запуск насоса по имени канала на заданное время
 * 
 * @param channel_name Имя канала насоса
 * @param duration_ms Длительность работы (мс)
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_NOT_FOUND если канал не найден
 */
esp_err_t pump_driver_run(const char *channel_name, uint32_t duration_ms);

/**
 * @brief Запуск насоса с заданной дозой (мл)
 * 
 * @param channel_name Имя канала насоса
 * @param dose_ml Доза в миллилитрах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_dose(const char *channel_name, float dose_ml);

/**
 * @brief Остановка насоса
 * 
 * @param channel_name Имя канала насоса
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_stop(const char *channel_name);

/**
 * @brief Аварийная остановка всех насосов
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t pump_driver_emergency_stop(void);

/**
 * @brief Получение текущего состояния насоса
 * 
 * @param channel_name Имя канала насоса
 * @param state Указатель для сохранения состояния
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_NOT_FOUND если канал не найден
 */
esp_err_t pump_driver_get_state(const char *channel_name, pump_driver_state_t *state);

/**
 * @brief Проверка, работает ли насос
 * 
 * @param channel_name Имя канала насоса
 * @return true если насос работает, false если нет или канал не найден
 */
bool pump_driver_is_running(const char *channel_name);

/**
 * @brief Проверка инициализации драйвера
 * 
 * @return true если драйвер инициализирован
 */
bool pump_driver_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // PUMP_DRIVER_H

