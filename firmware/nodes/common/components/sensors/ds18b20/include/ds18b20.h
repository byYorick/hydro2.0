/**
 * DS18B20 на одной шине 1-Wire (skip ROM, один датчик).
 * Внешняя подтяжка 4.7 кОм к 3.3 В обязательна.
 */
#ifndef DS18B20_H
#define DS18B20_H

#include "ds18b20_parse.h"

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t ds18b20_init(int gpio_num);
void ds18b20_deinit(void);
bool ds18b20_is_initialized(void);

/**
 * Неблокирующий опрос: первый вызов запускает Convert T и возвращает BUSY,
 * следующий после паузы конверсии читает scratchpad.
 * Любой статус кроме OK и BUSY — датчик недоступен, температуру не писать.
 */
ds18b20_status_t ds18b20_poll(float *temp_c);

/** Для test_sensor: ждёт конверсию внутри вызова. */
ds18b20_status_t ds18b20_read_blocking(float *temp_c);

#ifdef __cplusplus
}
#endif

#endif /* DS18B20_H */
