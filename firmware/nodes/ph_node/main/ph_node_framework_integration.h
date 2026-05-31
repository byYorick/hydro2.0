/**
 * @file ph_node_framework_integration.h
 * @brief Заголовочный файл для интеграции ph_node с node_framework
 */

#ifndef PH_NODE_FRAMEWORK_INTEGRATION_H
#define PH_NODE_FRAMEWORK_INTEGRATION_H

#include <stdbool.h>
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
 * Один опрос Trema pH за тик (аналог ec_node_ec_poll_sensor_once): лёгкий probe, init при необходимости,
 * trema_ph_read → снимок в очереди драйвера. MQTT/OLED — только trema_ph_try_cached_measurement.
 */
void ph_node_ph_poll_sensor_once(void);

/** Результат trema_ph_probe_chip_quick() в последнем ph_node_ph_poll_sensor_once() (OLED без полного discovery). */
bool ph_node_ph_last_poll_chip_present(void);

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void ph_node_framework_register_mqtt_handlers(void);

#ifdef __cplusplus
}
#endif

#endif // PH_NODE_FRAMEWORK_INTEGRATION_H

