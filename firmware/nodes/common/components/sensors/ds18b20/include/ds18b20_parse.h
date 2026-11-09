/**
 * Разбор scratchpad DS18B20 без шины 1-Wire.
 * Ошибки датчика не превращаются в температуру.
 */
#ifndef DS18B20_PARSE_H
#define DS18B20_PARSE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DS18B20_SCRATCHPAD_LEN 9
#define DS18B20_POWER_ON_RAW ((int16_t)0x0550)

typedef enum {
    DS18B20_OK = 0,
    DS18B20_ABSENT = 1,
    DS18B20_CRC = 2,
    DS18B20_POWER_ON = 3,
    DS18B20_IMPLAUSIBLE = 4,
    DS18B20_BUSY = 5
} ds18b20_status_t;

uint8_t ds18b20_crc8(const uint8_t *data, size_t len);

/**
 * Раствор: правдоподобно -10..60 °C.
 * Сырое 0x0550 (85.0 °C после сброса) — sensor_unavailable, даже если
 * конверсия формально уложилась в диапазон датчика.
 */
ds18b20_status_t ds18b20_parse_scratchpad(const uint8_t scratch[DS18B20_SCRATCHPAD_LEN], float *temp_c);

#ifdef __cplusplus
}
#endif

#endif /* DS18B20_PARSE_H */
