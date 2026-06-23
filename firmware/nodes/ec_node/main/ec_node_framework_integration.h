/**
 * @file ec_node_framework_integration.h
 * @brief Интеграция ec_node с node_framework
 * 
 * Этот файл связывает ec_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#ifndef EC_NODE_FRAMEWORK_INTEGRATION_H
#define EC_NODE_FRAMEWORK_INTEGRATION_H

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Инициализация интеграции ec_node с node_framework
 * 
 * Регистрирует обработчики команд и настраивает callbacks для:
 * - Обработки NodeConfig
 * - Обработки команд (run_pump, calibrate)
 * - Публикации телеметрии
 * 
 * @return ESP_OK при успехе
 */
esp_err_t ec_node_framework_init(void);

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 * 
 * Устанавливает callbacks для mqtt_manager для обработки config и command сообщений
 */
void ec_node_framework_register_mqtt_handlers(void);

/**
 * @brief Callback для публикации телеметрии EC
 * 
 * Используется в ec_node_tasks.c для периодической публикации телеметрии
 * 
 * @param user_ctx Пользовательский контекст (не используется)
 * @return ESP_OK при успехе
 */
esp_err_t ec_node_publish_telemetry_callback(void *user_ctx);

/**
 * Один опрос Trema EC за тик: probe, init/температура, trema_ec_read, trema_ec_get_tds (один раз),
 * push в очередь снимка (EC + raw + TDS ppm). Публикация MQTT и OLED — только из очереди, без
 * повторного trema_ec_read / trema_ec_get_tds в callback.
 */
void ec_node_ec_poll_sensor_once(void);

/** Результат trema_ec_probe_present() в последнем ec_node_ec_poll_sensor_once() (для OLED без второго probe). */
bool ec_node_ec_last_poll_probe_present(void);

#ifdef __cplusplus
}
#endif

#endif // EC_NODE_FRAMEWORK_INTEGRATION_H
