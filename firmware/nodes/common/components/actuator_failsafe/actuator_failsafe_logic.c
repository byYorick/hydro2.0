/**
 * @file actuator_failsafe_logic.c
 * @brief Debounce и защёлка E-STOP, пригодные для host-теста.
 */

#include "actuator_failsafe_logic.h"

#include <stddef.h>

void actuator_failsafe_logic_reset(actuator_failsafe_logic_t *state)
{
    if (state == NULL) {
        return;
    }
    state->seeded = false;
    state->debounced_pressed = false;
    state->candidate_pressed = false;
    state->candidate_since_us = 0;
    state->latched = false;
}

void actuator_failsafe_logic_seed(actuator_failsafe_logic_t *state, bool raw_pressed, int64_t now_us)
{
    if (state == NULL) {
        return;
    }
    state->seeded = true;
    state->debounced_pressed = raw_pressed;
    state->candidate_pressed = raw_pressed;
    state->candidate_since_us = now_us;
    state->latched = raw_pressed;
}

actuator_failsafe_edge_t actuator_failsafe_logic_step(
    actuator_failsafe_logic_t *state,
    bool raw_pressed,
    int64_t now_us,
    int64_t debounce_us
)
{
    if (state == NULL) {
        return ACTUATOR_FAILSAFE_EDGE_NONE;
    }
    if (!state->seeded) {
        actuator_failsafe_logic_seed(state, raw_pressed, now_us);
        return raw_pressed ? ACTUATOR_FAILSAFE_EDGE_PRESSED : ACTUATOR_FAILSAFE_EDGE_NONE;
    }
    if (debounce_us < 0) {
        debounce_us = 0;
    }

    if (raw_pressed != state->debounced_pressed) {
        if (raw_pressed != state->candidate_pressed) {
            state->candidate_pressed = raw_pressed;
            state->candidate_since_us = now_us;
        } else if ((now_us - state->candidate_since_us) >= debounce_us) {
            state->debounced_pressed = state->candidate_pressed;
        }
    } else {
        state->candidate_pressed = raw_pressed;
        state->candidate_since_us = now_us;
    }

    if (state->debounced_pressed && !state->latched) {
        state->latched = true;
        return ACTUATOR_FAILSAFE_EDGE_PRESSED;
    }
    if (state->debounced_pressed && state->latched) {
        return ACTUATOR_FAILSAFE_EDGE_HELD;
    }
    if (!state->debounced_pressed && state->latched) {
        state->latched = false;
        return ACTUATOR_FAILSAFE_EDGE_RELEASED;
    }
    return ACTUATOR_FAILSAFE_EDGE_NONE;
}

bool actuator_failsafe_logic_allows_energize(const actuator_failsafe_logic_t *state)
{
    return state != NULL && state->seeded && !state->latched;
}
