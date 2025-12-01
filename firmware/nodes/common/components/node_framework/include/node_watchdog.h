/**
 * @file node_watchdog.h
 * @brief Унифицированный менеджер watchdog для нод
 * 
 * Управление watchdog таймером:
 * - Инициализация watchdog с конфигурацией
 * - Регистрация задач в watchdog
 * - Обработка срабатывания watchdog (переход в safe_mode)
 * - Мониторинг времени выполнения задач
 */

#ifndef NODE_WATCHDOG_H
#define NODE_WATCHDOG_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация watchdog
 */
typedef struct {
    uint32_t timeout_ms;        ///< Таймаут watchdog в миллисекундах (по умолчанию 10000)
    bool trigger_panic;         ///< Вызывать panic при срабатывании (false = переход в safe_mode)
    uint32_t idle_core_mask;    ///< Маска ядер для мониторинга idle задач (0 = отключено)
} node_watchdog_config_t;

/**
 * @brief Инициализация watchdog менеджера
 * 
 * @param config Конфигурация watchdog (NULL для значений по умолчанию)
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_init(const node_watchdog_config_t *config);

/**
 * @brief Деинициализация watchdog менеджера
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_deinit(void);

/**
 * @brief Регистрация текущей задачи в watchdog
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_add_task(void);

/**
 * @brief Удаление текущей задачи из watchdog
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_remove_task(void);

/**
 * @brief Сброс watchdog таймера
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_reset(void);

/**
 * @brief Получение информации о времени работы задачи
 * 
 * @param task_name Имя задачи (NULL для текущей задачи)
 * @param runtime_ms Указатель для сохранения времени работы в миллисекундах
 * @return ESP_OK при успехе
 */
esp_err_t node_watchdog_get_task_runtime(const char *task_name, uint32_t *runtime_ms);

/**
 * @brief Проверка, инициализирован ли watchdog
 * 
 * @return true если инициализирован
 */
bool node_watchdog_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // NODE_WATCHDOG_H


