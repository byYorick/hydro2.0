/**
 * @file relay_node_framework_integration.h
 * @brief Заголовочный файл для интеграции relay_node с node_framework
 */

#ifndef RELAY_NODE_FRAMEWORK_INTEGRATION_H
#define RELAY_NODE_FRAMEWORK_INTEGRATION_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация node_framework для relay_node
 * 
 * @return ESP_OK при успехе
 */
esp_err_t relay_node_framework_init(void);

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void relay_node_framework_register_mqtt_handlers(void);

#ifdef __cplusplus
}
#endif

#endif // RELAY_NODE_FRAMEWORK_INTEGRATION_H

