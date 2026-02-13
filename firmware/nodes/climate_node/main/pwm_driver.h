/**
 * @file pwm_driver.h
 * @brief Простой LEDC PWM драйвер для climate_node
 */

#ifndef CLIMATE_PWM_DRIVER_H
#define CLIMATE_PWM_DRIVER_H

#include "esp_err.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация PWM канала
 */
typedef struct {
    const char *channel_name;   ///< Имя канала из NodeConfig
    int gpio_pin;               ///< GPIO вывод
    uint32_t frequency_hz;      ///< Частота PWM
    int resolution_bits;        ///< Разрешение таймера (4..15)
} pwm_driver_channel_config_t;

esp_err_t pwm_driver_init(const pwm_driver_channel_config_t *channels, size_t channel_count);
esp_err_t pwm_driver_init_from_config(void);
esp_err_t pwm_driver_deinit(void);
esp_err_t pwm_driver_set_duty_percent(const char *channel_name, float duty_percent);

#ifdef __cplusplus
}
#endif

#endif // CLIMATE_PWM_DRIVER_H
