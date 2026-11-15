/**
 * Host-тест link-loss storage_irrigation: таймаут гасит насос и клапаны,
 * reconnect не включает полив, конфиг 0/9/301 отклоняется, 10/30/300 принимается.
 *
 * gcc -std=c11 -Wall -Wextra -Werror -I firmware/nodes/common/components/config_storage/include \
 *   -I firmware/nodes/storage_irrigation_node/main \
 *   firmware/tests/host/test_storage_irr_link_loss.c \
 *   firmware/nodes/common/components/config_storage/link_loss_timeout.c \
 *   firmware/nodes/storage_irrigation_node/main/storage_irrigation_link_loss_logic.c
 */
#include "link_loss_timeout.h"
#include "storage_irrigation_link_loss_logic.h"

#include <stdio.h>

static int g_failures = 0;

static void expect_true(const char *name, bool value)
{
    if (!value) {
        fprintf(stderr, "FAIL: %s\n", name);
        g_failures++;
    }
}

static void expect_status(const char *name, link_loss_timeout_resolve_status_t actual, link_loss_timeout_resolve_status_t expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s (status %d, expected %d)\n", name, (int)actual, (int)expected);
        g_failures++;
    }
}

static void expect_u32(const char *name, uint32_t actual, uint32_t expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s (got %u, expected %u)\n", name, actual, expected);
        g_failures++;
    }
}

static link_loss_timeout_field_t number_field(double value)
{
    return link_loss_timeout_field_from_number(true, true, value);
}

static void expect_reject(const char *name, link_loss_timeout_field_t top, link_loss_timeout_field_t guards)
{
    uint32_t out = 123456u;
    link_loss_timeout_resolve_status_t status = link_loss_timeout_resolve(top, guards, &out);
    expect_status(name, status, LINK_LOSS_TIMEOUT_RESOLVE_REJECTED);
    expect_u32(name, out, 123456u);
}

static void expect_accept(const char *name, link_loss_timeout_field_t top, link_loss_timeout_field_t guards, uint32_t expected)
{
    uint32_t out = 0;
    link_loss_timeout_resolve_status_t status = link_loss_timeout_resolve(top, guards, &out);
    expect_status(name, status, LINK_LOSS_TIMEOUT_RESOLVE_ACCEPTED);
    expect_u32(name, out, expected);
}

static void test_timeout_bounds(void)
{
    link_loss_timeout_field_t absent = link_loss_timeout_field_absent();
    uint32_t out = 0;

    expect_status(
        "both absent defaults",
        link_loss_timeout_resolve(absent, absent, &out),
        LINK_LOSS_TIMEOUT_RESOLVE_DEFAULTED
    );
    expect_u32("default is 30", out, 30u);

    expect_accept("10 accepted", number_field(10.0), absent, 10u);
    expect_accept("30 accepted", number_field(30.0), absent, 30u);
    expect_accept("300 accepted", absent, number_field(300.0), 300u);
    expect_accept("mirrors 30/30", number_field(30.0), number_field(30.0), 30u);

    expect_reject("0 rejected", number_field(0.0), absent);
    expect_reject("9 rejected", number_field(9.0), absent);
    expect_reject("301 rejected", number_field(301.0), absent);
    expect_reject("negative rejected", number_field(-1.0), absent);
    expect_reject("fraction rejected", number_field(30.5), absent);
    expect_reject("non-number rejected", link_loss_timeout_field_from_number(true, false, 30.0), absent);
    expect_reject("guards 0 rejected even if top is 30", number_field(30.0), number_field(0.0));
    expect_reject("mismatched mirrors rejected", number_field(10.0), number_field(300.0));
}

enum {
    CH_PUMP = 0,
    CH_VALVE_CLEAN_FILL,
    CH_VALVE_CLEAN_SUPPLY,
    CH_VALVE_SOLUTION_FILL,
    CH_VALVE_SOLUTION_SUPPLY,
    CH_VALVE_IRRIGATION,
    CH_COUNT
};

static void test_safe_stop_and_no_resume(void)
{
    bool channels[CH_COUNT];
    bool command_active = true;
    size_t i;

    for (i = 0; i < CH_COUNT; i++) {
        channels[i] = true;
    }

    storage_irr_link_loss_safe_stop(channels, CH_COUNT, &command_active);
    expect_true("pump off after timeout", channels[CH_PUMP] == false);
    expect_true("clean fill valve off", channels[CH_VALVE_CLEAN_FILL] == false);
    expect_true("clean supply valve off", channels[CH_VALVE_CLEAN_SUPPLY] == false);
    expect_true("solution fill valve off", channels[CH_VALVE_SOLUTION_FILL] == false);
    expect_true("solution supply valve off", channels[CH_VALVE_SOLUTION_SUPPLY] == false);
    expect_true("irrigation valve off", channels[CH_VALVE_IRRIGATION] == false);
    expect_true("irrigation command interrupted", command_active == false);

    storage_irr_link_loss_on_link_restored(channels, CH_COUNT, &command_active);
    expect_true("reconnect leaves pump off", channels[CH_PUMP] == false);
    for (i = CH_VALVE_CLEAN_FILL; i < CH_COUNT; i++) {
        expect_true("reconnect leaves valve off", channels[i] == false);
    }
    expect_true("reconnect does not resume irrigation", command_active == false);

    channels[CH_PUMP] = true;
    channels[CH_VALVE_IRRIGATION] = true;
    command_active = true;
    storage_irr_link_loss_on_link_restored(channels, CH_COUNT, &command_active);
    expect_true("reconnect does not clear a still-running pump", channels[CH_PUMP] == true);
    expect_true("reconnect does not energize from a snapshot", channels[CH_VALVE_CLEAN_FILL] == false);
    expect_true("reconnect drops the resume flag", command_active == false);
}

int main(void)
{
    test_timeout_bounds();
    test_safe_stop_and_no_resume();
    if (g_failures != 0) {
        fprintf(stderr, "test_storage_irr_link_loss: %d failure(s)\n", g_failures);
        return 1;
    }
    printf("test_storage_irr_link_loss: ok\n");
    return 0;
}
