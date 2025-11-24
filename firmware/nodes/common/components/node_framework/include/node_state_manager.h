/**
 * @file node_state_manager.h
 * @brief Менеджер состояния ноды для фреймворка
 * 
 * Управление жизненным циклом ноды:
 * - init → running → error → safe_mode
 * - Автоматический переход в safe_mode при критических ошибках
 * - Мониторинг состояния
 */

#ifndef NODE_STATE_MANAGER_H
#define NODE_STATE_MANAGER_H

#include "esp_err.h"
#include "node_framework.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Уровень ошибки
 */
typedef enum {
    ERROR_LEVEL_WARNING = 0,   ///< Предупреждение (не критично)
    ERROR_LEVEL_ERROR = 1,      ///< Ошибка (требует внимания)
    ERROR_LEVEL_CRITICAL = 2    ///< Критическая ошибка (переход в safe_mode)
} error_level_t;

/**
 * @brief Инициализация менеджера состояния
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_init(void);

/**
 * @brief Деинициализация менеджера состояния
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_deinit(void);

/**
 * @brief Переход в безопасный режим
 * 
 * @param reason Причина перехода в safe_mode
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_enter_safe_mode(const char *reason);

/**
 * @brief Выход из безопасного режима
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_exit_safe_mode(void);

/**
 * @brief Регистрация ошибки (новая версия с уровнями)
 * 
 * @param level Уровень ошибки (WARNING, ERROR, CRITICAL)
 * @param component Компонент, в котором произошла ошибка
 * @param error_code Код ошибки
 * @param message Сообщение об ошибке
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_report_error(
    error_level_t level,
    const char *component,
    esp_err_t error_code,
    const char *message
);

/**
 * @brief Регистрация ошибки (старая версия для обратной совместимости)
 * 
 * @param component Компонент, в котором произошла ошибка
 * @param error_code Код ошибки
 * @param message Сообщение об ошибке
 * @param is_critical true если ошибка критическая (переход в safe_mode)
 * @return ESP_OK при успехе
 * @deprecated Используйте node_state_manager_report_error с error_level_t
 */
esp_err_t node_state_manager_report_error_legacy(
    const char *component,
    esp_err_t error_code,
    const char *message,
    bool is_critical
);

/**
 * @brief Получение количества ошибок
 * 
 * @param component Компонент (NULL для всех компонентов)
 * @return Количество ошибок
 */
uint32_t node_state_manager_get_error_count(const char *component);

/**
 * @brief Callback для отключения актуаторов при входе в safe_mode
 * 
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
typedef esp_err_t (*node_safe_mode_disable_actuators_callback_t)(void *user_ctx);

/**
 * @brief Регистрация callback для отключения актуаторов в safe_mode
 * 
 * @param callback Callback функция
 * @param user_ctx Пользовательский контекст
 * @return ESP_OK при успехе
 */
esp_err_t node_state_manager_register_safe_mode_callback(
    node_safe_mode_disable_actuators_callback_t callback,
    void *user_ctx
);

#ifdef __cplusplus
}
#endif

#endif // NODE_STATE_MANAGER_H

