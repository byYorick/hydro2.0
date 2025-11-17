/**
 * @file ph_node_telemetry.c
 * @brief Telemetry publishing implementation
 */

#include "ph_node_telemetry.h"
#include "ph_node_app.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "trema_ph.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"
#include <string.h>
#include <math.h>

static const char *TAG = "ph_node_telemetry";

void ph_node_publish_telemetry(void) {
    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }
    
    // Initialize sensor if not initialized
    if (!ph_node_is_ph_sensor_initialized() && i2c_bus_is_initialized()) {
        if (trema_ph_init()) {
            ph_node_set_ph_sensor_initialized(true);
            ESP_LOGI(TAG, "Trema pH sensor initialized");
        }
    }
    
    // Read pH value
    float ph_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    
    if (ph_node_is_ph_sensor_initialized()) {
        read_success = trema_ph_read(&ph_value);
        using_stub = trema_ph_is_using_stub_values();
        
        if (!read_success || isnan(ph_value)) {
            ESP_LOGW(TAG, "Failed to read pH value, using stub");
            ph_value = 6.5f;  // Neutral value
            using_stub = true;
        }
    } else {
        ESP_LOGW(TAG, "pH sensor not initialized, using stub value");
        ph_value = 6.5f;
        using_stub = true;
    }
    
    // Get node_id from config
    char node_id[64];
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        strncpy(node_id, "nd-ph-1", sizeof(node_id) - 1);
    }
    
    // Format according to MQTT_SPEC_FULL.md section 3.2
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "ph_sensor");
        cJSON_AddStringToObject(telemetry, "metric_type", "PH");
        cJSON_AddNumberToObject(telemetry, "value", ph_value);
        cJSON_AddNumberToObject(telemetry, "raw", (int)(ph_value * 1000));  // Raw value in thousandths
        cJSON_AddBoolToObject(telemetry, "stub", using_stub);  // Stub flag
        cJSON_AddNumberToObject(telemetry, "timestamp", (double)(esp_timer_get_time() / 1000000));
        
        // Add stability information if available
        if (ph_node_is_ph_sensor_initialized() && !using_stub) {
            bool is_stable = trema_ph_get_stability();
            cJSON_AddBoolToObject(telemetry, "stable", is_stable);
        }
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_manager_publish_telemetry("ph_sensor", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

