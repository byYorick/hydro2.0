/**
 * Host-тест разбора DS18B20: CRC, 85 °C после сброса, неправдоподобные значения.
 */
#include "ds18b20_parse.h"

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

static void test_known_vectors(void)
{
    /* 25.0 °C, CRC посчитан независимо от прошивки (полином Dallas 0x8C). */
    const uint8_t ok25[DS18B20_SCRATCHPAD_LEN] = {0x90, 0x01, 0x00, 0x00, 0x00, 0x7F, 0x00, 0x00, 0x4B};
    const uint8_t power_on[DS18B20_SCRATCHPAD_LEN] = {0x50, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xD4};
    const uint8_t hot[DS18B20_SCRATCHPAD_LEN] = {0xD0, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xC8};
    uint8_t broken[DS18B20_SCRATCHPAD_LEN] = {0x90, 0x01, 0x00, 0x00, 0x00, 0x7F, 0x00, 0x00, 0x4B};
    float temp = 123.0f;

    expect_eq_int("crc 25c", ds18b20_crc8(ok25, 8), 0x4B);
    expect_eq_int("parse 25c", ds18b20_parse_scratchpad(ok25, &temp), DS18B20_OK);
    if (temp < 24.9f || temp > 25.1f) {
        fprintf(stderr, "FAIL temp 25 got %f\n", (double)temp);
        g_failures++;
    }

    temp = 0.0f;
    expect_eq_int("power-on 85", ds18b20_parse_scratchpad(power_on, &temp), DS18B20_POWER_ON);
    expect_eq_int("85 does not publish", temp == 0.0f, 1);

    broken[0] ^= 0x01u;
    expect_eq_int("crc mismatch", ds18b20_parse_scratchpad(broken, &temp), DS18B20_CRC);

    expect_eq_int("61c implausible", ds18b20_parse_scratchpad(hot, &temp), DS18B20_IMPLAUSIBLE);
    expect_eq_int("null scratch absent", ds18b20_parse_scratchpad(NULL, &temp), DS18B20_ABSENT);
}

int main(void)
{
    test_known_vectors();
    if (g_failures != 0) {
        fprintf(stderr, "%d assertion(s) failed\n", g_failures);
        return EXIT_FAILURE;
    }
    printf("test_ds18b20_parse: ok\n");
    return EXIT_SUCCESS;
}
