/**
 * @file pwm_driver.c
 * @brief Реализация LEDC PWM драйвера для climate_node
 */

#include "pwm_driver.h"
#include "config_storage.h"
#include "esp_log.h"
#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdbool.h>

static const char *TAG = "pwm_driver";

#define PWM_DRIVER_MAX_CHANNELS       LEDC_CHANNEL_MAX
#define PWM_DRIVER_DEFAULT_FREQ_HZ    5000
#define PWM_DRIVER_DEFAULT_RES_BITS   10

typedef struct {
    char channel_name[CONFIG_STORAGE_MAX_STRING_LEN];
    ledc_channel_t ledc_channel;
    ledc_mode_t speed_mode;
    ledc_timer_t timer;
    uint32_t max_duty;
    float duty_percent;
    bool initialized;
} pwm_channel_t;

static pwm_channel_t s_channels[PWM_DRIVER_MAX_CHANNELS] = {0};
static size_t s_channel_count = 0;
static bool s_timer_configured = false;
static ledc_timer_config_t s_timer_cfg = {0};
static SemaphoreHandle_t s_mutex = NULL;

static void pwm_driver_reset_state(void) {
    memset(s_channels, 0, sizeof(s_channels));
    s_channel_count = 0;
    s_timer_configured = false;
    if (s_mutex != NULL) {
        vSemaphoreDelete(s_mutex);
        s_mutex = NULL;
    }
}

static esp_err_t pwm_driver_configure_timer(uint32_t frequency_hz, int resolution_bits) {
    if (resolution_bits < 4) {
        resolution_bits = PWM_DRIVER_DEFAULT_RES_BITS;
    }

    ledc_timer_bit_t resolution = (ledc_timer_bit_t)resolution_bits;
    s_timer_cfg.speed_mode = LEDC_LOW_SPEED_MODE;
    s_timer_cfg.duty_resolution = resolution;
    s_timer_cfg.timer_num = LEDC_TIMER_0;
    s_timer_cfg.freq_hz = frequency_hz;
    s_timer_cfg.clk_cfg = LEDC_AUTO_CLK;

    esp_err_t err = ledc_timer_config(&s_timer_cfg);
    if (err == ESP_OK) {
        s_timer_configured = true;
    } else {
        ESP_LOGE(TAG, "Failed to configure LEDC timer: %s", esp_err_to_name(err));
    }
    return err;
}

static uint32_t pwm_driver_get_max_duty(void) {
    if (!s_timer_configured) {
        return 0;
    }
    return (1UL << s_timer_cfg.duty_resolution) - 1;
}

esp_err_t pwm_driver_init(const pwm_driver_channel_config_t *channels, size_t channel_count) {
    if (channels == NULL || channel_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    if (channel_count > PWM_DRIVER_MAX_CHANNELS) {
        ESP_LOGE(TAG, "Too many PWM channels: %zu (max %d)", channel_count, PWM_DRIVER_MAX_CHANNELS);
        return ESP_ERR_INVALID_ARG;
    }

    pwm_driver_reset_state();

    if (s_mutex == NULL) {
        s_mutex = xSemaphoreCreateMutex();
        if (s_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    uint32_t freq = channels[0].frequency_hz > 0 ? channels[0].frequency_hz : PWM_DRIVER_DEFAULT_FREQ_HZ;
    int resolution_bits = channels[0].resolution_bits > 0 ? channels[0].resolution_bits : PWM_DRIVER_DEFAULT_RES_BITS;
    esp_err_t err = pwm_driver_configure_timer(freq, resolution_bits);
    if (err != ESP_OK) {
        return err;
    }

    uint32_t max_duty = pwm_driver_get_max_duty();

    for (size_t i = 0; i < channel_count; i++) {
        pwm_channel_t *channel = &s_channels[i];
        memset(channel, 0, sizeof(pwm_channel_t));
        strncpy(channel->channel_name, channels[i].channel_name, sizeof(channel->channel_name) - 1);
        channel->ledc_channel = (ledc_channel_t)i;
        channel->speed_mode = s_timer_cfg.speed_mode;
        channel->timer = s_timer_cfg.timer_num;
        channel->max_duty = max_duty;
        channel->duty_percent = 0.0f;

        ledc_channel_config_t ch_cfg = {
            .gpio_num = channels[i].gpio_pin,
            .speed_mode = channel->speed_mode,
            .channel = channel->ledc_channel,
            .intr_type = LEDC_INTR_DISABLE,
            .timer_sel = channel->timer,
            .duty = 0,
            .hpoint = 0,
        };

        err = ledc_channel_config(&ch_cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure LEDC channel %s: %s", channel->channel_name, esp_err_to_name(err));
            pwm_driver_reset_state();
            return err;
        }

        channel->initialized = true;
        s_channel_count++;
        ESP_LOGI(TAG, "Configured PWM channel %s on GPIO %d", channel->channel_name, channels[i].gpio_pin);
    }

    return ESP_OK;
}

esp_err_t pwm_driver_init_from_config(void) {
    char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read NodeConfig from storage");
        return err;
    }

    cJSON *config = cJSON_Parse(config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Failed to parse NodeConfig JSON");
        return ESP_FAIL;
    }

    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels == NULL || !cJSON_IsArray(channels)) {
        cJSON_Delete(config);
        ESP_LOGW(TAG, "No channels array found in NodeConfig");
        return ESP_ERR_NOT_FOUND;
    }

    pwm_driver_channel_config_t channel_configs[PWM_DRIVER_MAX_CHANNELS];
    size_t cfg_count = 0;

    int channels_size = cJSON_GetArraySize(channels);
    for (int i = 0; i < channels_size && cfg_count < PWM_DRIVER_MAX_CHANNELS; i++) {
        cJSON *channel = cJSON_GetArrayItem(channels, i);
        if (channel == NULL || !cJSON_IsObject(channel)) {
            continue;
        }

        cJSON *type_item = cJSON_GetObjectItem(channel, "type");
        if (type_item == NULL || strcmp(type_item->valuestring, "ACTUATOR") != 0) {
            continue;
        }

        cJSON *actuator_type = cJSON_GetObjectItem(channel, "actuator_type");
        if (actuator_type == NULL || !cJSON_IsString(actuator_type)) {
            continue;
        }

        const char *actuator = actuator_type->valuestring;
        if (strcmp(actuator, "PWM") != 0 && strcmp(actuator, "FAN") != 0 && strcmp(actuator, "LED") != 0) {
            continue;
        }

        cJSON *name_item = cJSON_GetObjectItem(channel, "name");
        cJSON *gpio_item = cJSON_GetObjectItem(channel, "gpio");
        if (name_item == NULL || gpio_item == NULL || !cJSON_IsString(name_item) || !cJSON_IsNumber(gpio_item)) {
            continue;
        }

        cJSON *freq_item = cJSON_GetObjectItem(channel, "pwm_frequency_hz");
        cJSON *res_item = cJSON_GetObjectItem(channel, "pwm_resolution_bits");

        pwm_driver_channel_config_t *cfg = &channel_configs[cfg_count++];
        cfg->channel_name = name_item->valuestring;
        cfg->gpio_pin = (int)cJSON_GetNumberValue(gpio_item);
        cfg->frequency_hz = (freq_item != NULL && cJSON_IsNumber(freq_item)) ? (uint32_t)cJSON_GetNumberValue(freq_item) : PWM_DRIVER_DEFAULT_FREQ_HZ;
        cfg->resolution_bits = (res_item != NULL && cJSON_IsNumber(res_item)) ? (int)cJSON_GetNumberValue(res_item) : PWM_DRIVER_DEFAULT_RES_BITS;
    }

    if (cfg_count == 0) {
        cJSON_Delete(config);
        ESP_LOGW(TAG, "No PWM channels defined in NodeConfig");
        return ESP_ERR_NOT_FOUND;
    }

    esp_err_t init_err = pwm_driver_init(channel_configs, cfg_count);
    cJSON_Delete(config);
    return init_err;
}

static pwm_channel_t *pwm_driver_find_channel(const char *channel_name) {
    if (channel_name == NULL) {
        return NULL;
    }
    for (size_t i = 0; i < s_channel_count; i++) {
        if (s_channels[i].initialized && strcmp(s_channels[i].channel_name, channel_name) == 0) {
            return &s_channels[i];
        }
    }
    return NULL;
}

esp_err_t pwm_driver_set_duty_percent(const char *channel_name, float duty_percent) {
    if (!s_timer_configured || s_channel_count == 0) {
        ESP_LOGE(TAG, "PWM driver not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (duty_percent < 0.0f) {
        duty_percent = 0.0f;
    } else if (duty_percent > 100.0f) {
        duty_percent = 100.0f;
    }

    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to lock PWM driver");
        return ESP_ERR_TIMEOUT;
    }

    pwm_channel_t *channel = pwm_driver_find_channel(channel_name);
    if (channel == NULL) {
        xSemaphoreGive(s_mutex);
        ESP_LOGE(TAG, "PWM channel %s not found", channel_name);
        return ESP_ERR_NOT_FOUND;
    }

    uint32_t duty_value = (uint32_t)((duty_percent / 100.0f) * channel->max_duty);
    esp_err_t err = ledc_set_duty(channel->speed_mode, channel->ledc_channel, duty_value);
    if (err == ESP_OK) {
        err = ledc_update_duty(channel->speed_mode, channel->ledc_channel);
    }

    if (err == ESP_OK) {
        channel->duty_percent = duty_percent;
        ESP_LOGI(TAG, "Channel %s duty set to %.1f%%", channel->channel_name, duty_percent);
    } else {
        ESP_LOGE(TAG, "Failed to update duty for %s: %s", channel->channel_name, esp_err_to_name(err));
    }

    xSemaphoreGive(s_mutex);
    return err;
}
