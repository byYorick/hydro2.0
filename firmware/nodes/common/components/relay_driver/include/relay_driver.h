/**
 * @file relay_driver.h
 * @brief Драйвер для управления реле (оптоизолированные модули)
 * 
 * Компонент предоставляет интерфейс для управления реле:
 * - Инициализация каналов реле из NodeConfig
 * - Управление состоянием реле (OPEN/CLOSED)
 * - Поддержка NC (Normaly-Closed) и NO (Normaly-Open) реле
 * - Thread-safe доступ
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/HARDWARE_ARCH_FULL.md (раздел 5.4)
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md
 */

#ifndef RELAY_DRIVER_H
#define RELAY_DRIVER_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Тип реле
 */
typedef enum {
    RELAY_TYPE_NO = 0,  ///< Normaly-Open (нормально разомкнутое)
    RELAY_TYPE_NC = 1   ///< Normaly-Closed (нормально замкнутое)
} relay_type_t;

/**
 * @brief Состояние реле
 */
typedef enum {
    RELAY_STATE_OPEN = 0,   ///< Реле разомкнуто (насос OFF для NC, ON для NO)
    RELAY_STATE_CLOSED = 1  ///< Реле замкнуто (насос ON для NC, OFF для NO)
} relay_state_t;

/**
 * @brief Конфигурация канала реле
 */
typedef struct {
    const char *channel_name;  ///< Имя канала (из NodeConfig)
    int gpio_pin;              ///< GPIO пин для управления реле
    relay_type_t relay_type;   ///< Тип реле (NC или NO)
    bool active_high;          ///< true если активный уровень HIGH, false если LOW
} relay_channel_config_t;

/**
 * @brief Инициализация драйвера реле
 * 
 * @param channels Массив конфигураций каналов реле
 * @param channel_count Количество каналов
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t relay_driver_init(const relay_channel_config_t *channels, size_t channel_count);

/**
 * @brief Инициализация драйвера реле из NodeConfig
 * 
 * Читает конфигурацию каналов из NodeConfig и инициализирует реле
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t relay_driver_init_from_config(void);

/**
 * @brief Деинициализация драйвера реле
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t relay_driver_deinit(void);

/**
 * @brief Установить состояние реле по имени канала
 * 
 * @param channel_name Имя канала реле
 * @param state Состояние (OPEN или CLOSED)
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_NOT_FOUND если канал не найден
 */
esp_err_t relay_driver_set_state(const char *channel_name, relay_state_t state);

/**
 * @brief Получить текущее состояние реле
 * 
 * @param channel_name Имя канала реле
 * @param state Указатель для сохранения состояния
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_NOT_FOUND если канал не найден
 */
esp_err_t relay_driver_get_state(const char *channel_name, relay_state_t *state);

/**
 * @brief Проверить, инициализирован ли драйвер
 * 
 * @return true если драйвер инициализирован
 */
bool relay_driver_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // RELAY_DRIVER_H

