/**
 * @file ph_node_framework_integration.h
 * @brief Заголовочный файл для интеграции ph_node с node_framework
 */

#ifndef PH_NODE_FRAMEWORK_INTEGRATION_H
#define PH_NODE_FRAMEWORK_INTEGRATION_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация node_framework для ph_node
 * 
 * @return ESP_OK при успехе
 */
esp_err_t ph_node_framework_init(void);

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void ph_node_framework_register_mqtt_handlers(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_FRAMEWORK_INTEGRATION_H

