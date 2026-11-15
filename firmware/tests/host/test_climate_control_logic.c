/**
 * Host-тест гистерезиса вытяжки, set_position и хода фрамуги.
 */
#include "climate_control_logic.h"

#include <math.h>
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

static void test_set_position_validation(void)
{
    expect_eq_int("missing position",
                  climate_set_position_validate(false, 10.0, false, 0.0),
                  CLIMATE_CMD_INVALID);
    expect_eq_int("nan position",
                  climate_set_position_validate(true, NAN, false, 0.0),
                  CLIMATE_CMD_INVALID);
    expect_eq_int("above 100",
                  climate_set_position_validate(true, 100.1, false, 0.0),
                  CLIMATE_CMD_INVALID);
    expect_eq_int("negative",
                  climate_set_position_validate(true, -0.1, true, 25.0),
                  CLIMATE_CMD_INVALID);
    expect_eq_int("zero is valid",
                  climate_set_position_validate(true, 0.0, true, 0.0),
                  CLIMATE_CMD_OK);
    expect_eq_int("full open",
                  climate_set_position_validate(true, 100.0, false, 0.0),
                  CLIMATE_CMD_OK);
    expect_eq_int("bad max step",
                  climate_set_position_validate(true, 40.0, true, 101.0),
                  CLIMATE_CMD_INVALID);
    expect_eq_int("step omitted",
                  climate_set_position_validate(true, 40.0, false, NAN),
                  CLIMATE_CMD_OK);
    expect_eq_int("ae step 25",
                  climate_position_apply_step(10, 80, true, 25),
                  35);
    expect_eq_int("no step clamp",
                  climate_position_apply_step(10, 80, false, 0),
                  80);
    expect_eq_int("zero step stays",
                  climate_position_apply_step(10, 80, true, 0),
                  10);
}

static void test_vent_travel_limits(void)
{
    vent_drive_t drive;
    vent_motor_t motor;

    vent_drive_init(&drive, 10000u, 1000u);
    expect_eq_int("unknown command accepted", vent_drive_command(&drive, 50, 2), CLIMATE_CMD_OK);
    expect_eq_int("busy while moving", vent_drive_command(&drive, 80, 2), CLIMATE_CMD_BUSY);
    motor = vent_drive_step(&drive, 10000u, false, false, false);
    expect_eq_int("still opening inside budget", motor, VENT_OPEN);

    motor = vent_drive_step(&drive, 1000u, false, false, false);
    expect_eq_int("time arrival stops", motor, VENT_STOP);
    expect_true("position known", drive.known);
    expect_eq_int("estimated 50", drive.position_pct, 50);
    expect_eq_int("same target no effect", vent_drive_command(&drive, 50, 2), CLIMATE_CMD_NO_EFFECT);

    expect_eq_int("close command", vent_drive_command(&drive, 0, 0), CLIMATE_CMD_OK);
    motor = vent_drive_step(&drive, 20000u, false, false, false);
    expect_eq_int("close without limit faults", motor, VENT_STOP);
    expect_true("fault latched", drive.fault);
    expect_eq_int("fault rejects next command", vent_drive_command(&drive, 20, 0), CLIMATE_CMD_ERROR);

    vent_drive_init(&drive, 10000u, 1000u);
    drive.known = true;
    drive.position_pct = 40;
    expect_eq_int("close from known", vent_drive_command(&drive, 0, 0), CLIMATE_CMD_OK);
    motor = vent_drive_step(&drive, 100u, true, false, false);
    expect_eq_int("closed limit stops", motor, VENT_STOP);
    expect_eq_int("closed reads zero", drive.position_pct, 0);
    expect_true("closed is known", drive.known);
    expect_true("limit is not a fault", !drive.fault);

    vent_drive_init(&drive, 10000u, 1000u);
    drive.known = true;
    drive.position_pct = 0;
    (void)vent_drive_command(&drive, 100, 0);
    motor = vent_drive_step(&drive, 50u, false, false, true);
    expect_eq_int("driver fault stops", motor, VENT_STOP);
    expect_true("driver fault flag", drive.fault);
    expect_true("position forgotten after driver fault", !drive.known);
}

int main(void)
{
    test_set_position_validation();
    test_vent_travel_limits();
    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_climate_control_logic: ok\n");
    return EXIT_SUCCESS;
}
