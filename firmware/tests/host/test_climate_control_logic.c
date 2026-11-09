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

static climate_fs_input_t base_input(void)
{
    climate_fs_input_t in;
    in.estop = false;
    in.driver_ok = true;
    in.sensor_valid = true;
    in.temp_c = 22.0f;
    in.link_up = true;
    in.safe_mode = CLIMATE_SAFE_VENTILATE_ABOVE;
    in.ventilate_above_c = 25.0f;
    in.overheat_c = 32.0f;
    in.failsafe_open_pct = 100;
    in.cool_close_c = 23.0f;
    return in;
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

static void test_exhaust_hysteresis(void)
{
    exhaust_hyst_t fan;
    fan.on_c = 25.0f;
    fan.off_c = 23.0f;
    fan.fan_on = false;

    expect_eq_int("below off stays off", exhaust_hysteresis_step(&fan, true, 22.0f), EXHAUST_OFF);
    expect_eq_int("between stays off", exhaust_hysteresis_step(&fan, true, 24.0f), EXHAUST_OFF);
    expect_eq_int("on threshold", exhaust_hysteresis_step(&fan, true, 25.0f), EXHAUST_ON);
    expect_eq_int("hold above off", exhaust_hysteresis_step(&fan, true, 24.0f), EXHAUST_ON);
    expect_eq_int("release at off", exhaust_hysteresis_step(&fan, true, 23.0f), EXHAUST_OFF);
    expect_eq_int("sensor loss forces on", exhaust_hysteresis_step(&fan, false, 22.0f), EXHAUST_ON);
    fan.on_c = 20.0f;
    fan.off_c = 20.0f;
    expect_eq_int("bad band fails on", exhaust_hysteresis_step(&fan, true, 18.0f), EXHAUST_ON);
}

static void test_failsafe_policy(void)
{
    climate_fs_input_t in = base_input();
    climate_fs_output_t out;

    climate_failsafe_decide(&in, false, &out);
    expect_eq_int("link up leaves vents to remote", out.reason, CLIMATE_FS_NORMAL);
    expect_true("no vent override", !out.override_remote);
    expect_true("fan follows request off", !out.exhaust_on);

    in.temp_c = 33.0f;
    climate_failsafe_decide(&in, false, &out);
    expect_eq_int("overheat", out.reason, CLIMATE_FS_OVERHEAT);
    expect_eq_int("overheat opens fully", out.vent_target_pct, 100);
    expect_true("overheat fan on", out.exhaust_on);
    expect_true("overheat overrides remote", out.move_vents && out.override_remote);

    in = base_input();
    in.link_up = false;
    in.temp_c = 27.0f;
    climate_failsafe_decide(&in, true, &out);
    expect_eq_int("link loss hot", out.reason, CLIMATE_FS_LINK);
    expect_eq_int("link loss ventilates", out.vent_target_pct, 100);
    expect_true("link loss fan stays on", out.exhaust_on);

    in.temp_c = 21.0f;
    climate_failsafe_decide(&in, false, &out);
    expect_eq_int("link loss cool closes", out.vent_target_pct, 0);
    expect_true("cool close moves", out.move_vents);

    in = base_input();
    in.sensor_valid = false;
    in.link_up = false;
    climate_failsafe_decide(&in, false, &out);
    expect_eq_int("sensor loss", out.reason, CLIMATE_FS_SENSOR);
    expect_eq_int("sensor loss opens", out.vent_target_pct, 100);
    expect_true("sensor loss fan", out.exhaust_on);

    in.safe_mode = CLIMATE_SAFE_ALL_OFF;
    climate_failsafe_decide(&in, true, &out);
    expect_true("configured all-off", out.deenergize_all && !out.exhaust_on);

    in = base_input();
    in.estop = true;
    in.temp_c = 40.0f;
    in.link_up = false;
    climate_failsafe_decide(&in, true, &out);
    expect_eq_int("estop wins over heat", out.reason, CLIMATE_FS_ESTOP);
    expect_true("estop deenergizes", out.deenergize_all && !out.exhaust_on && !out.move_vents);

    in = base_input();
    in.driver_ok = false;
    climate_failsafe_decide(&in, true, &out);
    expect_eq_int("driver fault", out.reason, CLIMATE_FS_DRIVER);
    expect_true("driver stops motor", out.deenergize_all && !out.move_vents);
}

int main(void)
{
    test_set_position_validation();
    test_vent_travel_limits();
    test_exhaust_hysteresis();
    test_failsafe_policy();
    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_climate_control_logic: ok\n");
    return EXIT_SUCCESS;
}
