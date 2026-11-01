/**
 * @file actuator_failsafe_logic.h
 * @brief Чистая логика debounce/защёлки E-STOP без ESP-IDF.
 *
 * Host-тест: firmware/tests/host/test_actuator_failsafe_logic.c
 */

#ifndef ACTUATOR_FAILSAFE_LOGIC_H
#define ACTUATOR_FAILSAFE_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool seeded;
    bool debounced_pressed;
    bool candidate_pressed;
    int64_t candidate_since_us;
    bool latched;
} actuator_failsafe_logic_t;

typedef enum {
    ACTUATOR_FAILSAFE_EDGE_NONE = 0,
    ACTUATOR_FAILSAFE_EDGE_PRESSED,
    ACTUATOR_FAILSAFE_EDGE_HELD,
    ACTUATOR_FAILSAFE_EDGE_RELEASED,
} actuator_failsafe_edge_t;

void actuator_failsafe_logic_reset(actuator_failsafe_logic_t *state);

/**
 * Первый отсчёт без ожидания debounce: зажатая при boot/reset кнопка
 * сразу ставит защёлку.
 */
void actuator_failsafe_logic_seed(actuator_failsafe_logic_t *state, bool raw_pressed, int64_t now_us);

actuator_failsafe_edge_t actuator_failsafe_logic_step(
    actuator_failsafe_logic_t *state,
    bool raw_pressed,
    int64_t now_us,
    int64_t debounce_us
);

/** Включение актуатора разрешено только после seed и при снятой защёлке. */
bool actuator_failsafe_logic_allows_energize(const actuator_failsafe_logic_t *state);

#ifdef __cplusplus
}
#endif

#endif /* ACTUATOR_FAILSAFE_LOGIC_H */
