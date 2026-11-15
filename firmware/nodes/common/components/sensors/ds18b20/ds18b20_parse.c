#include "ds18b20_parse.h"

#include <math.h>

uint8_t ds18b20_crc8(const uint8_t *data, size_t len)
{
    uint8_t crc = 0;
    size_t i;
    int bit;

    if (data == NULL) {
        return 0;
    }
    for (i = 0; i < len; i++) {
        crc ^= data[i];
        for (bit = 0; bit < 8; bit++) {
            if ((crc & 0x01u) != 0u) {
                crc = (uint8_t)((crc >> 1) ^ 0x8Cu);
            } else {
                crc = (uint8_t)(crc >> 1);
            }
        }
    }
    return crc;
}

ds18b20_status_t ds18b20_parse_scratchpad(const uint8_t scratch[DS18B20_SCRATCHPAD_LEN], float *temp_c)
{
    int16_t raw;
    float temp;

    if (scratch == NULL || temp_c == NULL) {
        return DS18B20_ABSENT;
    }
    if (ds18b20_crc8(scratch, 8) != scratch[8]) {
        return DS18B20_CRC;
    }
    raw = (int16_t)((uint16_t)scratch[0] | ((uint16_t)scratch[1] << 8));
    if (raw == DS18B20_POWER_ON_RAW) {
        return DS18B20_POWER_ON;
    }
    temp = (float)raw / 16.0f;
    if (!isfinite(temp) || temp < -10.0f || temp > 60.0f) {
        return DS18B20_IMPLAUSIBLE;
    }
    *temp_c = temp;
    return DS18B20_OK;
}
