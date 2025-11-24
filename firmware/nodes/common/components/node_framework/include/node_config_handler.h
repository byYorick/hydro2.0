/**
 * @file node_config_handler.h
 * @brief Обработчик NodeConfig для фреймворка нод
 * 
 * Унифицированная обработка NodeConfig:
 * - Парсинг JSON
 * - Валидация обязательных полей
 * - Применение конфигурации
 * - Формирование config_response
 */

#ifndef NODE_CONFIG_HANDLER_H
#define NODE_CONFIG_HANDLER_H

#include "esp_err.h"
#include "cJSON.h"
#include "node_framework.h"

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
 * @brief Публикация ответа на конфиг
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

#ifdef __cplusplus
}
#endif

#endif // NODE_CONFIG_HANDLER_H

