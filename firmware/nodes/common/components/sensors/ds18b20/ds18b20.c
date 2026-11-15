#include "ds18b20.h"

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define DS18B20_CMD_SKIP_ROM 0xCC
#define DS18B20_CMD_CONVERT 0x44
#define DS18B20_CMD_READ_SCRATCH 0xBE
#define DS18B20_CONVERT_WAIT_US 750000

static int s_gpio = -1;
static bool s_convert_pending = false;
static int64_t s_convert_started_us = 0;

static void ow_drive_low(void)
{
    gpio_set_direction((gpio_num_t)s_gpio, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)s_gpio, 0);
}

static void ow_release(void)
{
    gpio_set_direction((gpio_num_t)s_gpio, GPIO_MODE_INPUT);
}

static bool ow_reset(void)
{
    bool present;

    ow_drive_low();
    esp_rom_delay_us(480);
    ow_release();
    esp_rom_delay_us(70);
    present = gpio_get_level((gpio_num_t)s_gpio) == 0;
    esp_rom_delay_us(410);
    return present;
}

static void ow_write_bit(int bit)
{
    ow_drive_low();
    if (bit) {
        esp_rom_delay_us(6);
        ow_release();
        esp_rom_delay_us(64);
    } else {
        esp_rom_delay_us(60);
        ow_release();
        esp_rom_delay_us(10);
    }
}

static int ow_read_bit(void)
{
    int bit;

    ow_drive_low();
    esp_rom_delay_us(6);
    ow_release();
    esp_rom_delay_us(9);
    bit = gpio_get_level((gpio_num_t)s_gpio);
    esp_rom_delay_us(55);
    return bit;
}

static void ow_write_byte(uint8_t value)
{
    int i;

    for (i = 0; i < 8; i++) {
        ow_write_bit(value & 0x01);
        value >>= 1;
    }
}

static uint8_t ow_read_byte(void)
{
    uint8_t value = 0;
    int i;

    for (i = 0; i < 8; i++) {
        if (ow_read_bit()) {
            value |= (uint8_t)(1u << i);
        }
    }
    return value;
}

static bool ow_start_convert(void)
{
    if (!ow_reset()) {
        return false;
    }
    ow_write_byte(DS18B20_CMD_SKIP_ROM);
    ow_write_byte(DS18B20_CMD_CONVERT);
    return true;
}

static ds18b20_status_t ow_read_temp(float *temp_c)
{
    uint8_t scratch[DS18B20_SCRATCHPAD_LEN];
    int i;

    if (!ow_reset()) {
        return DS18B20_ABSENT;
    }
    ow_write_byte(DS18B20_CMD_SKIP_ROM);
    ow_write_byte(DS18B20_CMD_READ_SCRATCH);
    for (i = 0; i < DS18B20_SCRATCHPAD_LEN; i++) {
        scratch[i] = ow_read_byte();
    }
    return ds18b20_parse_scratchpad(scratch, temp_c);
}

esp_err_t ds18b20_init(int gpio_num)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << gpio_num,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    if (gpio_num < 0 || gpio_num >= GPIO_NUM_MAX) {
        return ESP_ERR_INVALID_ARG;
    }
    if (gpio_config(&cfg) != ESP_OK) {
        return ESP_FAIL;
    }
    s_gpio = gpio_num;
    s_convert_pending = false;
    s_convert_started_us = 0;
    return ESP_OK;
}

void ds18b20_deinit(void)
{
    s_gpio = -1;
    s_convert_pending = false;
}

bool ds18b20_is_initialized(void)
{
    return s_gpio >= 0;
}

ds18b20_status_t ds18b20_poll(float *temp_c)
{
    int64_t now;

    if (s_gpio < 0 || temp_c == NULL) {
        return DS18B20_ABSENT;
    }
    now = esp_timer_get_time();
    if (!s_convert_pending) {
        if (!ow_start_convert()) {
            return DS18B20_ABSENT;
        }
        s_convert_pending = true;
        s_convert_started_us = now;
        return DS18B20_BUSY;
    }
    if ((now - s_convert_started_us) < DS18B20_CONVERT_WAIT_US) {
        return DS18B20_BUSY;
    }
    s_convert_pending = false;
    return ow_read_temp(temp_c);
}

ds18b20_status_t ds18b20_read_blocking(float *temp_c)
{
    ds18b20_status_t status;

    if (s_gpio < 0 || temp_c == NULL) {
        return DS18B20_ABSENT;
    }
    s_convert_pending = false;
    if (!ow_start_convert()) {
        return DS18B20_ABSENT;
    }
    vTaskDelay(pdMS_TO_TICKS(800));
    status = ow_read_temp(temp_c);
    return status;
}
