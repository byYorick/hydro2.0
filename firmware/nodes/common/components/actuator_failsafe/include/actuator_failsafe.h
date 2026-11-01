/**
 * @file actuator_failsafe.h
 * @brief Общий аппаратный E-STOP для актуаторных нод (ph / ec / pump).
 *
 * Пока вход защёлкнут, включение актуаторов запрещено. Safe-OFF делает
 * callback ноды (обычно pump_driver_force_deenergize): прямая запись GPIO
 * не зависит от мьютекса драйвера. Отпускание кнопки снимает защёлку и
 * не восстанавливает предыдущее состояние выходов.
 */

#ifndef ACTUATOR_FAILSAFE_H
#define ACTUATOR_FAILSAFE_H

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ACTUATOR_FAILSAFE_DEFAULT_DEBOUNCE_MS 80U
#define ACTUATOR_FAILSAFE_POLL_PERIOD_MS 20U

typedef esp_err_t (*actuator_failsafe_safe_state_fn)(void *ctx);

typedef struct {
    int gpio_pin;
    bool active_low;
    uint32_t debounce_ms;
    actuator_failsafe_safe_state_fn safe_state_cb;
    void *safe_state_ctx;
} actuator_failsafe_config_t;

/**
 * Настраивает вход, снимает первый отсчёт (зажатая кнопка латчит сразу),
 * один раз вызывает safe-state (boot/reset) и запускает опрос.
 * Повторный вызов после успеха — ESP_OK без переконфигурации.
 */
esp_err_t actuator_failsafe_init(const actuator_failsafe_config_t *config);

/** true, пока E-STOP защёлкнут. До успешного init — false. */
bool actuator_failsafe_is_latched(void);

/**
 * Вызывает safe-state callback. Ошибка callback логируется и возвращается
 * вызывающему; GPIO-часть callback должна уже быть выполнена внутри него.
 */
esp_err_t actuator_failsafe_force_safe_state(void);

#ifdef __cplusplus
}
#endif

#endif /* ACTUATOR_FAILSAFE_H */
