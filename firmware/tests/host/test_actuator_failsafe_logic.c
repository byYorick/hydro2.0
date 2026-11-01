/**
 * Host-тест защёлки E-STOP (SAF-02).
 * gcc -Wall -Wextra -Werror -I ../../nodes/common/components/actuator_failsafe/include \
 *   -o /tmp/test_actuator_failsafe_logic test_actuator_failsafe_logic.c \
 *   ../../nodes/common/components/actuator_failsafe/actuator_failsafe_logic.c
 */
#include "actuator_failsafe_logic.h"

#include <stdio.h>
#include <stdlib.h>

static int g_failures = 0;

static void expect_eq_int(const char *name, int actual, int expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL %s: got %d expected %d\n", name, actual, expected);
        g_failures++;
    }
}

static void expect_true(const char *name, bool value)
{
    if (!value) {
        fprintf(stderr, "FAIL %s\n", name);
        g_failures++;
    }
}

static void expect_false(const char *name, bool value)
{
    if (value) {
        fprintf(stderr, "FAIL %s\n", name);
        g_failures++;
    }
}

int main(void)
{
    actuator_failsafe_logic_t state;
    const int64_t debounce_us = 80 * 1000;

    actuator_failsafe_logic_reset(&state);
    expect_false("unseeded denies energize", actuator_failsafe_logic_allows_energize(&state));

    expect_eq_int("boot released",
                  actuator_failsafe_logic_step(&state, false, 0, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_NONE);
    expect_true("released allows energize", actuator_failsafe_logic_allows_energize(&state));

    actuator_failsafe_logic_reset(&state);
    expect_eq_int("boot pressed latches immediately",
                  actuator_failsafe_logic_step(&state, true, 1000, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_PRESSED);
    expect_false("boot latch blocks energize", actuator_failsafe_logic_allows_energize(&state));
    expect_eq_int("held stays latched",
                  actuator_failsafe_logic_step(&state, true, 2000, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_HELD);

    actuator_failsafe_logic_reset(&state);
    (void)actuator_failsafe_logic_step(&state, false, 0, debounce_us);
    expect_eq_int("short press does not latch",
                  actuator_failsafe_logic_step(&state, true, 1000, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_NONE);
    expect_true("short press still allows energize", actuator_failsafe_logic_allows_energize(&state));
    expect_eq_int("press confirmed after debounce",
                  actuator_failsafe_logic_step(&state, true, 1000 + debounce_us, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_PRESSED);
    expect_false("confirmed press blocks energize", actuator_failsafe_logic_allows_energize(&state));

    expect_eq_int("release glitch ignored",
                  actuator_failsafe_logic_step(&state, false, 1000 + debounce_us + 10, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_HELD);
    expect_false("glitch keeps latch", actuator_failsafe_logic_allows_energize(&state));
    expect_eq_int("release after debounce clears latch",
                  actuator_failsafe_logic_step(&state, false, 1000 + (debounce_us * 2) + 10, debounce_us),
                  ACTUATOR_FAILSAFE_EDGE_RELEASED);
    expect_true("release allows a new command", actuator_failsafe_logic_allows_energize(&state));
    expect_false("release does not stay latched", state.latched);

    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_actuator_failsafe_logic: ok\n");
    return EXIT_SUCCESS;
}
