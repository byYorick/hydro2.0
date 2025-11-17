/**
 * @file ph_node_setup.c
 * @brief Setup portal wrapper for ph_node
 */

#include "ph_node_setup.h"
#include "setup_portal.h"
#include "esp_log.h"

static const char *TAG = "ph_node_setup";

void ph_node_run_setup_mode(void) {
    ESP_LOGI(TAG, "Starting setup mode for PH node");
    
    setup_portal_full_config_t config = {
        .node_type_prefix = "PH",
        .ap_password = "hydro2025",
        .enable_oled = true,
        .oled_user_ctx = NULL
    };
    
    // This function will block until credentials are received and device reboots
    setup_portal_run_full_setup(&config);
}

