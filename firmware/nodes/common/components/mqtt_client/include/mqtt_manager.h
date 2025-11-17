/**
 * @file mqtt_manager.h
 * @brief MQTT менеджер для ESP32-нод
 * 
 * Компонент обеспечивает подключение к MQTT брокеру, подписки на топики,
 * публикацию сообщений и автоматический реконнект согласно:
 * - doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md
 * - doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 * 
 * Соответствие стандартам:
 * - Именование: snake_case с префиксом mqtt_manager_
 * - Обработка ошибок: все функции возвращают esp_err_t
 * - Логирование: через ESP_LOG* с тегом "mqtt_manager"
 */

#ifndef MQTT_MANAGER_H
#define MQTT_MANAGER_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#include "esp_event.h"
#include "mqtt_client.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Структура параметров подключения к MQTT брокеру
 */
typedef struct {
    const char *host;           ///< IP адрес или hostname брокера
    uint16_t port;              ///< Порт брокера (обычно 1883 или 8883)
    uint16_t keepalive;         ///< Keepalive интервал в секундах
    const char *client_id;      ///< MQTT client ID (если NULL, используется node_id)
    const char *username;       ///< Имя пользователя (может быть NULL)
    const char *password;       ///< Пароль (может быть NULL)
    bool use_tls;               ///< Использовать TLS
} mqtt_manager_config_t;

/**
 * @brief Структура параметров узла для формирования топиков
 */
typedef struct {
    const char *gh_uid;         ///< UID теплицы (например "gh-1")
    const char *zone_uid;       ///< UID зоны (например "zn-3")
    const char *node_uid;       ///< UID узла (например "nd-ph-1")
} mqtt_node_info_t;

/**
 * @brief Callback для обработки входящих MQTT сообщений (config)
 * 
 * @param topic MQTT топик
 * @param data Данные сообщения (JSON)
 * @param data_len Длина данных
 * @param user_ctx Пользовательский контекст
 */
typedef void (*mqtt_config_callback_t)(const char *topic, const char *data, int data_len, void *user_ctx);

/**
 * @brief Callback для обработки входящих MQTT сообщений (command)
 * 
 * @param topic MQTT топик
 * @param channel Имя канала из топика
 * @param data Данные сообщения (JSON)
 * @param data_len Длина данных
 * @param user_ctx Пользовательский контекст
 */
typedef void (*mqtt_command_callback_t)(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);

/**
 * @brief Callback для событий подключения/отключения
 * 
 * @param connected true если подключен, false если отключен
 * @param user_ctx Пользовательский контекст
 */
typedef void (*mqtt_connection_callback_t)(bool connected, void *user_ctx);

/**
 * @brief Инициализация MQTT менеджера
 * 
 * @param config Параметры подключения к брокеру
 * @param node_info Информация об узле для формирования топиков
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_init(const mqtt_manager_config_t *config, const mqtt_node_info_t *node_info);

/**
 * @brief Запуск MQTT менеджера
 * 
 * Подключается к брокеру и подписывается на топики config и command
 * 
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_start(void);

/**
 * @brief Остановка MQTT менеджера
 * 
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_stop(void);

/**
 * @brief Освобождение ресурсов MQTT менеджера
 * 
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_deinit(void);

/**
 * @brief Регистрация callback для обработки config сообщений
 * 
 * @param cb Callback функция
 * @param user_ctx Пользовательский контекст
 */
void mqtt_manager_register_config_cb(mqtt_config_callback_t cb, void *user_ctx);

/**
 * @brief Регистрация callback для обработки command сообщений
 * 
 * @param cb Callback функция
 * @param user_ctx Пользовательский контекст
 */
void mqtt_manager_register_command_cb(mqtt_command_callback_t cb, void *user_ctx);

/**
 * @brief Регистрация callback для событий подключения
 * 
 * @param cb Callback функция
 * @param user_ctx Пользовательский контекст
 */
void mqtt_manager_register_connection_cb(mqtt_connection_callback_t cb, void *user_ctx);

/**
 * @brief Публикация телеметрии
 * 
 * Топик: hydro/{gh}/{zone}/{node}/{channel}/telemetry
 * QoS: 1, Retain: false
 * 
 * @param channel Имя канала
 * @param data JSON данные телеметрии
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_publish_telemetry(const char *channel, const char *data);

/**
 * @brief Публикация статуса узла
 * 
 * Топик: hydro/{gh}/{zone}/{node}/status
 * QoS: 1, Retain: true
 * 
 * @param data JSON данные статуса
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_publish_status(const char *data);

/**
 * @brief Публикация heartbeat
 * 
 * Топик: hydro/{gh}/{zone}/{node}/heartbeat
 * QoS: 0, Retain: false
 * 
 * @param data JSON данные heartbeat
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_publish_heartbeat(const char *data);

/**
 * @brief Публикация ответа на команду
 * 
 * Топик: hydro/{gh}/{zone}/{node}/{channel}/command_response
 * QoS: 1, Retain: false
 * 
 * @param channel Имя канала
 * @param data JSON данные ответа
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_publish_command_response(const char *channel, const char *data);

/**
 * @brief Публикация ответа на конфигурацию
 * 
 * Топик: hydro/{gh}/{zone}/{node}/config_response
 * QoS: 1, Retain: false
 * 
 * @param data JSON данные ответа
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_publish_config_response(const char *data);

/**
 * @brief Проверка подключения к MQTT брокеру
 * 
 * @return true если подключен
 */
bool mqtt_manager_is_connected(void);

/**
 * @brief Переподключение к MQTT брокеру
 * 
 * @return ESP_OK при успехе
 */
esp_err_t mqtt_manager_reconnect(void);

#ifdef __cplusplus
}
#endif

#endif // MQTT_MANAGER_H

