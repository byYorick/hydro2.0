#ifndef NODE_PWM_COMMAND_H
#define NODE_PWM_COMMAND_H

#include <math.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

typedef enum {
    NODE_PWM_LEGACY_RAW,
    NODE_PWM_LEGACY_PERCENT_OR_RAW
} node_pwm_legacy_scale_t;

typedef struct {
    float percent;
    uint8_t raw;
} node_pwm_value_t;

/* duty is always percent. Preserve each node's historical value scale. */
static inline bool node_pwm_decode(bool has_duty, double duty,
                                   bool has_value, double value,
                                   node_pwm_legacy_scale_t legacy_scale,
                                   node_pwm_value_t *out) {
    if (out == NULL) {
        return false;
    }
    if (has_duty) {
        if (!isfinite(duty) || duty < 0.0 || duty > 100.0) {
            return false;
        }
        out->percent = (float)duty;
        out->raw = (uint8_t)lround(duty * 255.0 / 100.0);
        return true;
    }
    if (!has_value || !isfinite(value)) {
        return false;
    }
    if (legacy_scale == NODE_PWM_LEGACY_PERCENT_OR_RAW && value < 0.0) {
        return false;
    }
    /* Clamp before conversion: a large JSON number must not overflow int. */
    int raw = value <= 0.0 ? 0 : value >= 255.0 ? 255 : (int)value;
    if (legacy_scale == NODE_PWM_LEGACY_PERCENT_OR_RAW && raw <= 100) {
        out->percent = (float)raw;
        out->raw = (uint8_t)lround(raw * 255.0 / 100.0);
    } else {
        out->raw = (uint8_t)raw;
        out->percent = (float)(raw * 100.0 / 255.0);
    }
    return true;
}

#endif
