/**
 * @file node_framework.h
 * @brief Унифицированный базовый фреймворк для нод ESP32
 * 
 * Фреймворк предоставляет единый API для:
 * - Обработки NodeConfig
 * - Обработки команд
 * - Публикации телеметрии
 * - Управления состоянием ноды
 * 
 * Это устраняет дублирование кода между разными нодами (ph_node, ec_node, climate_node, pump_node).
 */

#ifndef NODE_FRAMEWORK_H
#define NODE_FRAMEWORK_H

#include "esp_err.h"
#include "cJSON.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Состояния жизненного цикла ноды
 */
typedef enum {
    NODE_STATE_INIT,        // Инициализация
    NODE_STATE_RUNNING,     // Нормальная работа
    NODE_STATE_ERROR,       // Ошибка (некритическая)
    NODE_STATE_SAFE_MODE    // Безопасный режим (критическая ошибка)
} node_state_t;

/**
 * @brief Типы метрик телеметрии
 */
typedef enum {
    METRIC_TYPE_PH,
    METRIC_TYPE_EC,
    METRIC_TYPE_TEMPERATURE,
    METRIC_TYPE_HUMIDITY,
    METRIC_TYPE_CURRENT,
    METRIC_TYPE_PUMP_STATE,
    METRIC_TYPE_CUSTOM  // Для пользовательских типов
} metric_type_t;

/**
 * @brief Callback для обработки специфичной логики ноды при применении конфига
 * 
 * @param channel_name Имя канала из конфига
 * @param channel_config JSON конфигурация канала
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
typedef esp_err_t (*node_config_channel_callback_t)(
    const char *channel_name,
    const cJSON *channel_config,
    void *user_ctx
);

/**
 * @brief Callback для обработки команд
 * 
 * @param channel Имя канала
 * @param cmd_name Имя команды
 * @param params Параметры команды (JSON)
 * @param response Указатель на JSON ответ (будет создан и заполнен)
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
typedef esp_err_t (*node_command_handler_t)(
    const char *channel,
    const char *cmd_name,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
);

/**
 * @brief Callback для публикации телеметрии (специфичная логика ноды)
 * 
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
typedef esp_err_t (*node_telemetry_callback_t)(void *user_ctx);

/**
 * @brief Конфигурация фреймворка
 */
typedef struct {
    const char *node_type;              // Тип ноды: "ph", "ec", "climate", "pump"
    const char *default_node_id;        // Дефолтный node_id
    const char *default_gh_uid;         // Дефолтный gh_uid
    const char *default_zone_uid;       // Дефолтный zone_uid
    
    // Callbacks для специфичной логики ноды
    node_config_channel_callback_t channel_init_cb;  // Инициализация каналов
    node_command_handler_t command_handler_cb;      // Обработка команд (опционально, можно регистрировать через API)
    node_telemetry_callback_t telemetry_cb;         // Публикация телеметрии (опционально)
    
    void *user_ctx;  // Пользовательский контекст для callbacks
} node_framework_config_t;

/**
 * @brief Инициализация фреймворка
 * 
 * @param config Конфигурация фреймворка
 * @return ESP_OK при успехе
 */
esp_err_t node_framework_init(const node_framework_config_t *config);

/**
 * @brief Деинициализация фреймворка
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_framework_deinit(void);

/**
 * @brief Получение текущего состояния ноды
 * 
 * @return Текущее состояние
 */
node_state_t node_framework_get_state(void);

/**
 * @brief Установка состояния ноды
 * 
 * @param state Новое состояние
 * @return ESP_OK при успехе
 */
esp_err_t node_framework_set_state(node_state_t state);

/**
 * @brief Проверка, находится ли нода в безопасном режиме
 * 
 * @return true если в safe_mode
 */
bool node_framework_is_safe_mode(void);

/**
 * @brief Получение типа ноды, заданного при инициализации фреймворка
 * 
 * @return Строка типа ноды (например, "ph", "ec", "climate", "pump") или NULL
 */
const char *node_framework_get_node_type(void);

#ifdef __cplusplus
}
#endif

#endif // NODE_FRAMEWORK_H
