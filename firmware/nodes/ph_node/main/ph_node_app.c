/**
 * @file ph_node_app.c
 * @brief Main application logic for ph_node
 * 
 * pH node for measuring pH and controlling acid/base pumps
 * According to NODE_ARCH_FULL.md and MQTT_SPEC_FULL.md
 */

#include "ph_node_app.h"
#include "ph_node_init.h"
#include "ph_node_tasks.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ph_node";

// Global state
static bool s_ph_sensor_initialized = false;
static bool s_oled_ui_initialized = false;
static bool s_pump_control_initialized = false;
static char s_node_id[64] = "nd-ph-1";

// State getters/setters
bool ph_node_is_ph_sensor_initialized(void) {
    return s_ph_sensor_initialized;
}

void ph_node_set_ph_sensor_initialized(bool initialized) {
    s_ph_sensor_initialized = initialized;
}

bool ph_node_is_oled_initialized(void) {
    return s_oled_ui_initialized;
}

void ph_node_set_oled_initialized(bool initialized) {
    s_oled_ui_initialized = initialized;
}

bool ph_node_is_pump_control_initialized(void) {
    return s_pump_control_initialized;
}

void ph_node_set_pump_control_initialized(bool initialized) {
    s_pump_control_initialized = initialized;
}

const char* ph_node_get_node_id(void) {
    return s_node_id;
}

void ph_node_set_node_id(const char *node_id) {
    if (node_id) {
        strncpy(s_node_id, node_id, sizeof(s_node_id) - 1);
        s_node_id[sizeof(s_node_id) - 1] = '\0';
    }
}

/**
 * @brief Initialize ph_node application
 */
void ph_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing ph_node application...");
    
    esp_err_t err = ph_node_init_components();
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Failed to initialize components: %s", esp_err_to_name(err));
        return;
    }
    
    // If setup mode was triggered, it will reboot the device
    if (err == ESP_ERR_NOT_FOUND) {
        return;
    }
    
    ESP_LOGI(TAG, "ph_node application initialized");
    
    // Start FreeRTOS tasks for sensor polling and heartbeat
    ph_node_start_tasks();
}
