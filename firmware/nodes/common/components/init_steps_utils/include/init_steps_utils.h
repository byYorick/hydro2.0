/**
 * @file init_steps_utils.h
 * @brief Общие утилиты для init-steps нод
 */

#ifndef INIT_STEPS_UTILS_H
#define INIT_STEPS_UTILS_H

#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cJSON cJSON;

typedef cJSON *(*init_steps_build_channels_fn)(void);

/**
 * @brief Получить строковый параметр из config_storage с дефолтом
 *
 * @param key Ключ ("node_id", "gh_uid", "zone_uid")
 * @param buffer Буфер для результата
 * @param buffer_size Размер буфера
 * @param default_value Значение по умолчанию (может быть NULL)
 * @return ESP_OK при успехе
 */
esp_err_t init_steps_utils_get_config_string(
    const char *key,
    char *buffer,
    size_t buffer_size,
    const char *default_value
);

/**
 * @brief Патч каналов и лимитов для pump-нод (pH/EC)
 *
 * @param build_channels Callback для сборки channels
 * @param current_min_ma Минимальный ток (mA)
 * @param current_max_ma Максимальный ток (mA)
 * @return ESP_OK при успехе
 */
esp_err_t init_steps_utils_patch_pump_config(
    init_steps_build_channels_fn build_channels,
    uint32_t current_min_ma,
    uint32_t current_max_ma
);

#ifdef __cplusplus
}
#endif

#endif // INIT_STEPS_UTILS_H
