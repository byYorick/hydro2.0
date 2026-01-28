/**
 * @file node_config_handler.h
 * @brief Обработчик NodeConfig для фреймворка нод
 * 
 * Унифицированная обработка NodeConfig:
 * - Парсинг JSON
 * - Валидация обязательных полей
 * - Применение конфигурации
 * - Формирование ответа на изменения конфига и публикация config_report
 */

#ifndef NODE_CONFIG_HANDLER_H
#define NODE_CONFIG_HANDLER_H

#include "esp_err.h"
#include "cJSON.h"
#include "node_framework.h"
#include "config_apply.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Обработка входящего NodeConfig
 * 
 * @param topic MQTT топик
 * @param data JSON данные конфига
 * @param data_len Длина данных
 * @param user_ctx Пользовательский контекст
 */
void node_config_handler_process(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
);

/**
 * @brief Валидация NodeConfig
 * 
 * @param config JSON конфиг
 * @param error_msg Буфер для сообщения об ошибке
 * @param error_msg_size Размер буфера
 * @return ESP_OK при валидном конфиге
 */
esp_err_t node_config_handler_validate(
    const cJSON *config,
    char *error_msg,
    size_t error_msg_size
);

/**
 * @brief Применение конфигурации
 * 
 * @param config JSON конфиг
 * @param previous_config Предыдущий конфиг (для сравнения)
 * @return ESP_OK при успехе
 */
esp_err_t node_config_handler_apply(
    const cJSON *config,
    const cJSON *previous_config
);

/**
 * @brief Применение конфигурации с возвратом результата
 * 
 * @param config JSON конфиг
 * @param previous_config Предыдущий конфиг (для сравнения)
 * @param result Указатель на структуру для заполнения результата (может быть NULL)
 * @return ESP_OK при успехе
 */
esp_err_t node_config_handler_apply_with_result(
    const cJSON *config,
    const cJSON *previous_config,
    config_apply_result_t *result
);

/**
 * @brief Публикация результата применения конфига
 * 
 * @param status Статус: "ACK" или "ERROR"
 * @param error_msg Сообщение об ошибке (если status == "ERROR")
 * @param restarted_components Массив имен перезапущенных компонентов (может быть NULL)
 * @param component_count Количество компонентов
 * @return ESP_OK при успехе
 */
esp_err_t node_config_handler_publish_response(
    const char *status,
    const char *error_msg,
    const char **restarted_components,
    size_t component_count
);

/**
 * @brief Callback для формирования списка каналов в ответе на конфиг.
 *
 * Владелец callback должен вернуть cJSON массив. node_config_handler берет
 * владение объектом и освободит его после публикации.
 */
typedef cJSON *(*node_config_channels_callback_t)(void *user_ctx);

/**
 * @brief Регистрация callback для формирования channels в ответе на конфиг.
 *
 * Если callback не задан, handler попытается взять channels из сохраненного NodeConfig.
 *
 * @param callback Callback для формирования channels (может быть NULL)
 * @param user_ctx Пользовательский контекст
 */
void node_config_handler_set_channels_callback(
    node_config_channels_callback_t callback,
    void *user_ctx
);

// Forward declarations для типов из mqtt_manager.h
typedef void (*mqtt_config_callback_t)(const char *topic, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_command_callback_t)(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_connection_callback_t)(bool connected, void *user_ctx);

/**
 * @brief Регистрация MQTT callbacks для config_apply_mqtt
 * 
 * Эта функция позволяет node_config_handler автоматически переподключать MQTT
 * при изменении MQTT настроек в NodeConfig.
 * 
 * @param config_cb Callback для обработки config сообщений
 * @param command_cb Callback для обработки command сообщений
 * @param connection_cb Callback для обработки изменений подключения
 * @param user_ctx Пользовательский контекст
 * @param default_node_id Дефолтный node_id
 * @param default_gh_uid Дефолтный gh_uid
 * @param default_zone_uid Дефолтный zone_uid
 */
void node_config_handler_set_mqtt_callbacks(
    mqtt_config_callback_t config_cb,
    mqtt_command_callback_t command_cb,
    mqtt_connection_callback_t connection_cb,
    void *user_ctx,
    const char *default_node_id,
    const char *default_gh_uid,
    const char *default_zone_uid
);

#ifdef __cplusplus
}
#endif

#endif // NODE_CONFIG_HANDLER_H
