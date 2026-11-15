/**
 * Host-тест лимитов дозы ph/ec.
 * gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
 *   -I firmware/nodes/common/components/dose_limit/include \
 *   firmware/tests/host/test_dose_limit.c \
 *   firmware/nodes/common/components/dose_limit/dose_limit.c \
 *   -lm -o /tmp/test_dose_limit
 */
#include "dose_limit.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_failures = 0;

static void expect_true(const char *name, bool value)
{
    if (!value) {
        fprintf(stderr, "FAIL %s\n", name);
        g_failures++;
    }
}

static void expect_eq_int(const char *name, int actual, int expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL %s: got %d expected %d\n", name, actual, expected);
        g_failures++;
    }
}

static void expect_eq_i32(const char *name, int32_t actual, int32_t expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL %s: got %ld expected %ld\n", name, (long)actual, (long)expected);
        g_failures++;
    }
}

static dose_limit_field_t number_field(double value)
{
    return dose_limit_field_from_number(true, true, value);
}

static void bind_pair(dose_limit_state_t *state, const char *name, int32_t per_milli, int32_t daily_milli)
{
    dose_limit_init(state);
    expect_true("bind", dose_limit_bind(state, name, per_milli, daily_milli));
}

static bool pump_started(const dose_limit_result_t *result)
{
    return result->pump_allowed;
}

static void test_per_dose_boundary(void)
{
    dose_limit_state_t state;
    dose_limit_result_t result;
    const int64_t now = 360000000;
    bool started = false;

    bind_pair(&state, "pump_acid", 20 * DOSE_LIMIT_MILLI_PER_ML, 100 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int(
        "exact per-dose allowed",
        dose_limit_authorize(&state, "pump_acid", 20.0, now, true, &result),
        DOSE_LIMIT_ALLOW
    );
    started = pump_started(&result);
    expect_true("exact per-dose starts pump", started);
    expect_eq_i32("exact per-dose used", result.used_milli, 20 * DOSE_LIMIT_MILLI_PER_ML);

    bind_pair(&state, "pump_acid", 20 * DOSE_LIMIT_MILLI_PER_ML, 100 * DOSE_LIMIT_MILLI_PER_ML);
    started = false;
    expect_eq_int(
        "above per-dose refused",
        dose_limit_authorize(&state, "pump_acid", 20.001, now, true, &result),
        DOSE_LIMIT_PER_DOSE
    );
    if (pump_started(&result)) {
        started = true;
    }
    expect_true("above per-dose does not start pump", !started);
    expect_eq_int("per-dose code", strcmp(dose_limit_error_code(result.code), DOSE_LIMIT_ERR_PER_DOSE), 0);
    expect_eq_i32("per-dose limit", result.limit_milli, 20 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_i32("per-dose requested", result.requested_milli, 20001);
    expect_eq_i32("per-dose used stays zero", result.used_milli, 0);
    expect_eq_i32("per-dose remaining is the cap", result.remaining_milli, 20 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_i32(
        "refused dose is not stored",
        dose_limit_active_used_milli(&state, "pump_acid", now, true),
        0
    );
}

static void test_daily_boundary_and_channels(void)
{
    dose_limit_state_t state;
    dose_limit_result_t result;
    const int64_t now = 360000000;
    bool started = false;

    dose_limit_init(&state);
    expect_true("bind acid", dose_limit_bind(&state, "pump_acid", 30 * DOSE_LIMIT_MILLI_PER_ML, 40 * DOSE_LIMIT_MILLI_PER_ML));
    expect_true("bind base", dose_limit_bind(&state, "pump_base", 30 * DOSE_LIMIT_MILLI_PER_ML, 40 * DOSE_LIMIT_MILLI_PER_ML));

    expect_eq_int("first 20 allowed", dose_limit_authorize(&state, "pump_acid", 20.0, now, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int("daily exact allowed", dose_limit_authorize(&state, "pump_acid", 20.0, now + 10, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_i32("daily exact used", result.used_milli, 40 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_i32("daily exact remaining", result.remaining_milli, 0);

    expect_eq_int(
        "one milli over daily refused",
        dose_limit_authorize(&state, "pump_acid", 0.001, now + 20, true, &result),
        DOSE_LIMIT_DAILY
    );
    if (pump_started(&result)) {
        started = true;
    }
    expect_true("daily refusal does not start pump", !started);
    expect_eq_int("daily code", strcmp(dose_limit_error_code(result.code), DOSE_LIMIT_ERR_DAILY), 0);
    expect_eq_i32("daily limit field", result.limit_milli, 40 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_i32("daily used unchanged", result.used_milli, 40 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_i32("daily remaining zero", result.remaining_milli, 0);
    expect_eq_i32(
        "base channel is independent",
        dose_limit_active_used_milli(&state, "pump_base", now, true),
        0
    );
    expect_eq_int("base still allows its own dose", dose_limit_authorize(&state, "pump_base", 20.0, now, true, &result), DOSE_LIMIT_ALLOW);
}

static void test_rolling_window(void)
{
    dose_limit_state_t state;
    dose_limit_result_t result;
    const int64_t t0 = 360000000;

    bind_pair(&state, "pump_a", 80 * DOSE_LIMIT_MILLI_PER_ML, 100 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int("window seed", dose_limit_authorize(&state, "pump_a", 60.0, t0, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int(
        "inside 24h refused",
        dose_limit_authorize(&state, "pump_a", 50.0, t0 + (12 * DOSE_LIMIT_HOUR_SEC), true, &result),
        DOSE_LIMIT_DAILY
    );
    expect_true("inside window pump stays off", !pump_started(&result));
    expect_eq_i32("inside window used", result.used_milli, 60 * DOSE_LIMIT_MILLI_PER_ML);

    expect_eq_int(
        "after 25h the hour bucket expires",
        dose_limit_authorize(&state, "pump_a", 50.0, t0 + (25 * DOSE_LIMIT_HOUR_SEC), true, &result),
        DOSE_LIMIT_ALLOW
    );
    expect_true("expired window starts pump", pump_started(&result));
    expect_eq_i32("only the new dose remains", result.used_milli, 50 * DOSE_LIMIT_MILLI_PER_ML);
}

static void test_clock_step_back_keeps_usage(void)
{
    dose_limit_state_t state;
    dose_limit_result_t result;
    const int64_t t0 = 360000000;

    bind_pair(&state, "pump_acid", 50 * DOSE_LIMIT_MILLI_PER_ML, 50 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int("dose before step", dose_limit_authorize(&state, "pump_acid", 40.0, t0 + (10 * DOSE_LIMIT_HOUR_SEC), true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int(
        "step back still counts the dose",
        dose_limit_authorize(&state, "pump_acid", 20.0, t0, true, &result),
        DOSE_LIMIT_DAILY
    );
    expect_true("step back does not start pump", !pump_started(&result));
    expect_eq_i32("step back used", result.used_milli, 40 * DOSE_LIMIT_MILLI_PER_ML);
}

static void test_reboot_no_double_count(void)
{
    dose_limit_state_t original;
    dose_limit_state_t restored;
    dose_limit_result_t result;
    uint8_t blob[DOSE_LIMIT_BLOB_MAX];
    size_t len = 0;
    const int64_t now = 360000000;
    bool started = false;

    bind_pair(&original, "pump_c", 80 * DOSE_LIMIT_MILLI_PER_ML, 200 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int("before reboot", dose_limit_authorize(&original, "pump_c", 30.0, now, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int("same hour second dose", dose_limit_authorize(&original, "pump_c", 10.0, now + 5, true, &result), DOSE_LIMIT_ALLOW);
    expect_true("export", dose_limit_export(&original, blob, sizeof(blob), &len));

    dose_limit_init(&restored);
    expect_true("rebind", dose_limit_bind(&restored, "pump_c", 80 * DOSE_LIMIT_MILLI_PER_ML, 200 * DOSE_LIMIT_MILLI_PER_ML));
    expect_true("import", dose_limit_import(&restored, blob, len));
    expect_true("reboot is trusted", !restored.ledger_untrusted);
    expect_eq_i32(
        "reboot keeps the sum",
        dose_limit_active_used_milli(&restored, "pump_c", now, true),
        40 * DOSE_LIMIT_MILLI_PER_ML
    );
    expect_eq_int("dose after reboot", dose_limit_authorize(&restored, "pump_c", 10.0, now + 8, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_i32("reboot did not double", result.used_milli, 50 * DOSE_LIMIT_MILLI_PER_ML);

    dose_limit_rollback(&original, "pump_c", 10.0, now + 5);
    expect_eq_i32(
        "rollback removes only the failed enqueue",
        dose_limit_active_used_milli(&original, "pump_c", now, true),
        30 * DOSE_LIMIT_MILLI_PER_ML
    );

    len = 0;
    expect_true("tiny export fails", !dose_limit_export(&original, blob, 4, &len));
    if (len != 0) {
        started = true;
    }
    expect_true("failed persist does not pretend a blob exists", !started);
}

static void test_unsynced_and_corrupt(void)
{
    dose_limit_state_t state;
    dose_limit_state_t restored;
    dose_limit_result_t result;
    uint8_t blob[DOSE_LIMIT_BLOB_MAX];
    size_t len = 0;
    const int64_t now = 360000000;
    bool started = false;

    bind_pair(&state, "pump_acid", 35 * DOSE_LIMIT_MILLI_PER_ML, 200 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int(
        "unsynced refuses even an empty window",
        dose_limit_authorize(&state, "pump_acid", 1.0, now, false, &result),
        DOSE_LIMIT_TIME_UNSYNCED
    );
    expect_true("unsynced pump stays off", !pump_started(&result));
    expect_eq_i32("unsynced remaining is zero", result.remaining_milli, 0);
    expect_eq_i32("unsynced stores nothing", dose_limit_active_used_milli(&state, "pump_acid", now, true), 0);
    expect_eq_int("zero timestamp refuses", dose_limit_authorize(&state, "pump_acid", 1.0, 0, true, &result), DOSE_LIMIT_TIME_UNSYNCED);

    expect_eq_int("synced dose", dose_limit_authorize(&state, "pump_acid", 5.0, now, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int(
        "later unsynced command does not add",
        dose_limit_authorize(&state, "pump_acid", 5.0, now + 1, false, &result),
        DOSE_LIMIT_TIME_UNSYNCED
    );
    expect_eq_i32("ledger unchanged while unsynced", result.used_milli, 5 * DOSE_LIMIT_MILLI_PER_ML);
    expect_true("export before corrupt", dose_limit_export(&state, blob, sizeof(blob), &len));
    blob[len / 2] ^= 0x5Au;

    dose_limit_init(&restored);
    expect_true("rebind after corrupt", dose_limit_bind(&restored, "pump_acid", 35 * DOSE_LIMIT_MILLI_PER_ML, 200 * DOSE_LIMIT_MILLI_PER_ML));
    expect_true("corrupt import fails", !dose_limit_import(&restored, blob, len));
    expect_true("corrupt ledger is untrusted", restored.ledger_untrusted);
    expect_eq_int(
        "corrupt window is full",
        dose_limit_authorize(&restored, "pump_acid", 1.0, now, true, &result),
        DOSE_LIMIT_DAILY
    );
    if (pump_started(&result)) {
        started = true;
    }
    expect_true("corrupt ledger does not start pump", !started);
    expect_eq_i32("corrupt remaining", result.remaining_milli, 0);
    expect_eq_i32("corrupt used reports the whole daily cap", result.used_milli, 200 * DOSE_LIMIT_MILLI_PER_ML);
}

static void test_alias_shares_channel(void)
{
    dose_limit_state_t state;
    dose_limit_result_t result;
    const int64_t now = 360000000;

    bind_pair(&state, "pump_acid", 20 * DOSE_LIMIT_MILLI_PER_ML, 20 * DOSE_LIMIT_MILLI_PER_ML);
    expect_eq_int("alias dose", dose_limit_authorize(&state, "ph_doser_down", 20.0, now, true, &result), DOSE_LIMIT_ALLOW);
    expect_eq_int("canonical sees alias", dose_limit_authorize(&state, "pump_acid", 0.1, now + 1, true, &result), DOSE_LIMIT_DAILY);
    expect_true("alias overflow pump off", !pump_started(&result));
}

static void test_config_validation(void)
{
    int32_t per_milli = 0;
    int32_t daily_milli = -1;
    const char *reason = "unset";
    dose_limit_channel_input_t channels[3];
    const char *bad_channel = NULL;

    expect_eq_int(
        "absent ph defaults",
        dose_limit_resolve_limits(
            DOSE_LIMIT_CHANNEL_PH,
            dose_limit_field_absent(),
            dose_limit_field_absent(),
            &per_milli,
            &daily_milli,
            &reason
        ),
        DOSE_LIMIT_CONFIG_OK
    );
    expect_eq_i32("ph default per", per_milli, DOSE_LIMIT_PH_DEFAULT_PER_DOSE_MILLI);
    expect_eq_i32("ph default daily", daily_milli, DOSE_LIMIT_PH_DEFAULT_DAILY_MILLI);

    expect_eq_int(
        "absent ec defaults",
        dose_limit_resolve_limits(
            DOSE_LIMIT_CHANNEL_EC,
            dose_limit_field_absent(),
            dose_limit_field_absent(),
            &per_milli,
            &daily_milli,
            &reason
        ),
        DOSE_LIMIT_CONFIG_OK
    );
    expect_eq_i32("ec default per", per_milli, DOSE_LIMIT_EC_DEFAULT_PER_DOSE_MILLI);
    expect_eq_i32("ec default daily", daily_milli, DOSE_LIMIT_EC_DEFAULT_DAILY_MILLI);

    per_milli = 123;
    daily_milli = 456;
    expect_eq_int(
        "zero per-dose rejects",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_PH, number_field(0.0), dose_limit_field_absent(), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_i32("zero does not clamp per", per_milli, 123);
    expect_eq_i32("zero does not clamp daily", daily_milli, 456);
    expect_true("zero reason", reason != NULL && strstr(reason, "max_dose_ml") != NULL);

    expect_eq_int(
        "negative daily rejects",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_EC, dose_limit_field_absent(), number_field(-5.0), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_int(
        "physical per-dose max accepted",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_PH, number_field(500.0), number_field(500.0), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_OK
    );
    expect_eq_i32("500 ml", per_milli, DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_MILLI);
    expect_eq_int(
        "above physical per-dose rejects",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_PH, number_field(500.001), number_field(600.0), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_i32("over-max does not clamp", per_milli, DOSE_LIMIT_PHYSICAL_MAX_PER_DOSE_MILLI);
    expect_eq_int(
        "physical daily max accepted",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_EC, number_field(80.0), number_field(2000.0), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_OK
    );
    expect_eq_i32("2000 ml", daily_milli, DOSE_LIMIT_PHYSICAL_MAX_DAILY_MILLI);
    expect_eq_int(
        "above physical daily rejects",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_EC, number_field(80.0), number_field(2000.001), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_int(
        "daily below per-dose rejects",
        dose_limit_resolve_limits(DOSE_LIMIT_CHANNEL_PH, number_field(40.0), number_field(30.0), &per_milli, &daily_milli, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_int(
        "non-number rejects",
        dose_limit_resolve_limits(
            DOSE_LIMIT_CHANNEL_PH,
            dose_limit_field_from_number(true, false, 10.0),
            dose_limit_field_absent(),
            &per_milli,
            &daily_milli,
            &reason
        ),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_eq_int(
        "nan rejects",
        dose_limit_resolve_limits(
            DOSE_LIMIT_CHANNEL_EC,
            number_field(NAN),
            dose_limit_field_absent(),
            &per_milli,
            &daily_milli,
            &reason
        ),
        DOSE_LIMIT_CONFIG_REJECT
    );

    memset(channels, 0, sizeof(channels));
    channels[0].name = "pump_base";
    channels[0].per_dose = number_field(10.0);
    channels[0].daily = number_field(50.0);
    channels[1].name = "fan_1";
    channels[1].per_dose = number_field(0.0);
    channels[1].daily = number_field(-1.0);
    channels[2].name = "pump_b";
    channels[2].per_dose = number_field(0.0);
    channels[2].daily = dose_limit_field_absent();
    expect_eq_int(
        "one bad dosing channel rejects the whole config",
        dose_limit_validate_channels(channels, 3, &bad_channel, &reason),
        DOSE_LIMIT_CONFIG_REJECT
    );
    expect_true("reject names the bad channel", bad_channel != NULL && strcmp(bad_channel, "pump_b") == 0);
    expect_eq_int(
        "non-dosing channel is ignored",
        dose_limit_validate_channels(channels, 2, &bad_channel, &reason),
        DOSE_LIMIT_CONFIG_OK
    );
}

int main(void)
{
    test_per_dose_boundary();
    test_daily_boundary_and_channels();
    test_rolling_window();
    test_clock_step_back_keeps_usage();
    test_reboot_no_double_count();
    test_unsynced_and_corrupt();
    test_alias_shares_channel();
    test_config_validation();

    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_dose_limit: ok\n");
    return EXIT_SUCCESS;
}
