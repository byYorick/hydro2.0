/**
 * @file wifi_manager.h
 * @brief Wi-Fi менеджер для ESP32-нод
 * 
 * Базовый Wi-Fi менеджер для подключения к сети
 * Согласно WIFI_CONNECTIVITY_ENGINE.md и NODE_ARCH_FULL.md
 */

#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация Wi-Fi
 */
typedef struct {
    const char *ssid;      ///< SSID сети
    const char *password; ///< Пароль сети
} wifi_manager_config_t;

/**
 * @brief Callback для событий подключения Wi-Fi
 * 
 * @param connected true если подключено, false если отключено
 * @param user_ctx Пользовательский контекст
 */
typedef void (*wifi_connection_cb_t)(bool connected, void *user_ctx);

/**
 * @brief Инициализация Wi-Fi менеджера
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t wifi_manager_init(void);

/**
 * @brief Подключение к Wi-Fi сети
 * 
 * @param config Конфигурация Wi-Fi (SSID и пароль)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t wifi_manager_connect(const wifi_manager_config_t *config);

/**
 * @brief Отключение от Wi-Fi сети
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t wifi_manager_disconnect(void);

/**
 * @brief Проверка статуса подключения
 * 
 * @return true если подключено
 */
bool wifi_manager_is_connected(void);

/**
 * @brief Получение RSSI
 * 
 * @param rssi Указатель для сохранения RSSI
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t wifi_manager_get_rssi(int8_t *rssi);

/**
 * @brief Регистрация callback для событий подключения
 * 
 * @param cb Callback функция
 * @param user_ctx Пользовательский контекст
 */
void wifi_manager_register_connection_cb(wifi_connection_cb_t cb, void *user_ctx);

/**
 * @brief Деинициализация Wi-Fi менеджера
 */
void wifi_manager_deinit(void);

#ifdef __cplusplus
}
#endif

#endif // WIFI_MANAGER_H



