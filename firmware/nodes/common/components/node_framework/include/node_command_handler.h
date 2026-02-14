/**
 * @file node_command_handler.h
 * @brief Обработчик команд для фреймворка нод
 * 
 * Унифицированная обработка команд:
 * - Парсинг JSON команд
 * - Валидация параметров
 * - Роутинг команд по обработчикам
 * - Формирование ACK/DONE/ERROR ответов
 */

#ifndef NODE_COMMAND_HANDLER_H
#define NODE_COMMAND_HANDLER_H

#include "esp_err.h"
#include "cJSON.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Максимальное количество зарегистрированных обработчиков команд
 */
#define NODE_COMMAND_HANDLER_MAX 16

/**
 * @brief Максимальная длина имени команды
 */
#define NODE_COMMAND_NAME_MAX_LEN 32

/**
 * @brief Обработчик команды
 * 
 * @param channel Имя канала
 * @param params Параметры команды (JSON)
 * @param response Указатель на JSON ответ (будет создан и заполнен)
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
typedef esp_err_t (*node_command_handler_func_t)(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
);

/**
 * @brief Регистрация обработчика команды
 * 
 * @param cmd_name Имя команды (например, "run_pump", "calibrate")
 * @param handler Функция-обработчик
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе, ESP_ERR_NO_MEM если нет места
 */
esp_err_t node_command_handler_register(
    const char *cmd_name,
    node_command_handler_func_t handler,
    void *user_ctx
);

/**
 * @brief Отмена регистрации обработчика команды
 * 
 * @param cmd_name Имя команды
 * @return ESP_OK при успехе
 */
esp_err_t node_command_handler_unregister(const char *cmd_name);

/**
 * @brief Обработка входящей команды
 * 
 * @param topic MQTT топик
 * @param channel Имя канала (извлечено из топика)
 * @param data JSON данные команды
 * @param data_len Длина данных
 * @param user_ctx Пользовательский контекст
 */
void node_command_handler_process(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
);

/**
 * @brief Извлечь cmd_id из params (если есть).
 *
 * @param params Параметры команды
 * @return Указатель на строку cmd_id или NULL
 */
const char *node_command_handler_get_cmd_id(const cJSON *params);

/**
 * @brief Опубликовать промежуточный статус ACK.
 *
 * @param cmd_id ID команды
 * @param channel Имя канала
 * @return ESP_OK при успехе
 */
esp_err_t node_command_handler_publish_accepted(const char *cmd_id, const char *channel);

/**
 * @brief Создание ответа на команду
 * 
 * @param cmd_id ID команды
 * @param status Статус: "ACK", "DONE" или "ERROR"
 * @param error_code Код ошибки (если status == "ERROR")
 * @param error_message Сообщение об ошибке (если status == "ERROR")
 * @param extra_data Дополнительные данные для ответа (может быть NULL)
 * @return JSON объект ответа (нужно удалить через cJSON_Delete)
 */
cJSON *node_command_handler_create_response(
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *error_message,
    const cJSON *extra_data
);

/**
 * @brief Проверка, была ли команда уже обработана (защита от дубликатов)
 * 
 * Использует LRU кеш per channel для отслеживания последних N cmd_id.
 * 
 * @param cmd_id ID команды
 * @param channel Имя канала (может быть NULL для "default")
 * @return true если команда уже обработана
 */
bool node_command_handler_is_duplicate(const char *cmd_id, const char *channel);

/**
 * @brief Получить сохраненный финальный статус команды из кеша
 * 
 * Используется для идемпотентности: при повторной команде возвращается сохраненный статус (DONE/ERROR).
 * 
 * @param cmd_id ID команды
 * @param channel Имя канала (может быть NULL для "default")
 * @return Указатель на строку статуса или NULL если команда не найдена или нет финального статуса
 */
const char *node_command_handler_get_cached_status(const char *cmd_id, const char *channel);

/**
 * @brief Сохранить финальный статус команды в кеш
 * 
 * Сохраняет терминальный статус (DONE/ERROR) для последующей идемпотентности.
 * 
 * @param cmd_id ID команды
 * @param channel Имя канала (может быть NULL для "default")
 * @param final_status Финальный статус (DONE/ERROR)
 */
void node_command_handler_cache_final_status(const char *cmd_id, const char *channel, const char *final_status);

/**
 * @brief Инициализация встроенных обработчиков команд
 * 
 * Регистрирует системные команды, такие как set_time
 */
void node_command_handler_init_builtin_handlers(void);

#ifdef __cplusplus
}
#endif

#endif // NODE_COMMAND_HANDLER_H
