/**
 * Host-тест политики SAF-01: таймаут мьютекса не отменяет de-energize.
 * Сборка: gcc -I../../nodes/storage_irrigation_node/main -o test_estop_lock_policy test_estop_lock_policy.c
 */
#include "estop_lock_policy.h"

#include <stdio.h>
#include <stdlib.h>

static int g_failures = 0;

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
    expect_true("pressed requires deenergize",
                estop_transition_requires_deenergize(true, false, false));
    expect_true("latched requires deenergize",
                estop_transition_requires_deenergize(false, true, false));
    expect_true("pending sync requires deenergize",
                estop_transition_requires_deenergize(false, false, true));
    expect_false("idle does not force outputs",
                 estop_transition_requires_deenergize(false, false, false));
    expect_false("lock failure must not skip deenergize",
                 estop_lock_failure_may_skip_deenergize());
    expect_true("pressed still requires deenergize when lock would fail",
                estop_transition_requires_deenergize(true, false, false)
                    && !estop_lock_failure_may_skip_deenergize());

    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_estop_lock_policy: ok\n");
    return EXIT_SUCCESS;
}
