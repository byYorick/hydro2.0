#ifndef CONFIG_APPLY_H
#define CONFIG_APPLY_H

#include <stddef.h>
#include "esp_err.h"
#include "cJSON.h"
#include "mqtt_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CONFIG_APPLY_MAX_COMPONENTS 8
#define CONFIG_APPLY_COMPONENT_NAME_MAX_LEN 16

typedef struct {
    char components[CONFIG_APPLY_MAX_COMPONENTS][CONFIG_APPLY_COMPONENT_NAME_MAX_LEN];
    size_t count;
} config_apply_result_t;

typedef struct {
    const char *default_node_id;
    const char *default_gh_uid;
    const char *default_zone_uid;
    mqtt_config_callback_t config_cb;
    mqtt_command_callback_t command_cb;
    mqtt_connection_callback_t connection_cb;
    void *user_ctx;
} config_apply_mqtt_params_t;

void config_apply_result_init(config_apply_result_t *result);

cJSON *config_apply_load_previous_config(void);

esp_err_t config_apply_wifi(const cJSON *new_config,
                            const cJSON *previous_config,
                            config_apply_result_t *result);

esp_err_t config_apply_wifi_with_mqtt_restart(const cJSON *new_config,
                                                const cJSON *previous_config,
                                                const config_apply_mqtt_params_t *mqtt_params,
                                                config_apply_result_t *result);

esp_err_t config_apply_mqtt(const cJSON *new_config,
                            const cJSON *previous_config,
                            const config_apply_mqtt_params_t *params,
                            config_apply_result_t *result);

esp_err_t config_apply_channels_pump(config_apply_result_t *result);

esp_err_t config_apply_channels_relay(config_apply_result_t *result);

#ifdef __cplusplus
}
#endif

#endif // CONFIG_APPLY_H
