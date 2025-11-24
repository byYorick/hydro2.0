/**
 * @file memory_pool.h
 * @brief Пул памяти для оптимизации использования памяти
 * 
 * Компонент предоставляет:
 * - Пул памяти для JSON объектов (cJSON)
 * - Пул памяти для JSON строк
 * - Метрики использования памяти
 * - Защиту от переполнения буферов
 */

#ifndef MEMORY_POOL_H
#define MEMORY_POOL_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация пула памяти
 */
typedef struct {
    size_t json_object_pool_size;    ///< Количество объектов в пуле JSON (по умолчанию 16)
    size_t json_string_pool_size;    ///< Количество строк в пуле JSON (по умолчанию 8)
    size_t json_string_max_len;      ///< Максимальная длина JSON строки (по умолчанию 512)
    bool enable_metrics;             ///< Включить сбор метрик (по умолчанию true)
} memory_pool_config_t;

/**
 * @brief Метрики использования памяти
 */
typedef struct {
    uint32_t json_objects_allocated;    ///< Количество выделенных JSON объектов
    uint32_t json_objects_freed;         ///< Количество освобожденных JSON объектов
    uint32_t json_strings_allocated;     ///< Количество выделенных JSON строк
    uint32_t json_strings_freed;         ///< Количество освобожденных JSON строк
    uint32_t pool_hits;                  ///< Попадания в пул (переиспользование)
    uint32_t pool_misses;                ///< Промахи пула (новое выделение)
    size_t current_heap_free;             ///< Текущая свободная память heap
    size_t min_heap_free;                 ///< Минимальная свободная память heap
} memory_pool_metrics_t;

/**
 * @brief Инициализация пула памяти
 * 
 * @param config Конфигурация пула (NULL для значений по умолчанию)
 * @return ESP_OK при успехе
 */
esp_err_t memory_pool_init(const memory_pool_config_t *config);

/**
 * @brief Деинициализация пула памяти
 * 
 * @return ESP_OK при успехе
 */
esp_err_t memory_pool_deinit(void);

/**
 * @brief Выделение JSON объекта из пула
 * 
 * @return Указатель на cJSON объект или NULL при ошибке
 * @note Используйте memory_pool_free_json_object() для освобождения
 */
void *memory_pool_alloc_json_object(void);

/**
 * @brief Освобождение JSON объекта в пул
 * 
 * @param obj Указатель на cJSON объект
 */
void memory_pool_free_json_object(void *obj);

/**
 * @brief Выделение буфера для JSON строки из пула
 * 
 * @param size Размер буфера (будет округлен до json_string_max_len)
 * @return Указатель на буфер или NULL при ошибке
 * @note Используйте memory_pool_free_json_string() для освобождения
 */
char *memory_pool_alloc_json_string(size_t size);

/**
 * @brief Освобождение буфера JSON строки в пул
 * 
 * @param str Указатель на буфер
 */
void memory_pool_free_json_string(char *str);

/**
 * @brief Получение метрик использования памяти
 * 
 * @param metrics Указатель для сохранения метрик
 * @return ESP_OK при успехе
 */
esp_err_t memory_pool_get_metrics(memory_pool_metrics_t *metrics);

/**
 * @brief Сброс метрик
 */
void memory_pool_reset_metrics(void);

/**
 * @brief Проверка, инициализирован ли пул
 * 
 * @return true если инициализирован
 */
bool memory_pool_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // MEMORY_POOL_H


