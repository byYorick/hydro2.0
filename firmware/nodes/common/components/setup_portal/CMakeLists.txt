idf_component_register(
    SRCS "setup_portal.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_http_server esp_wifi esp_netif nvs_flash json config_storage oled_ui i2c_bus freertos
    PRIV_REQUIRES esp_event node_utils
)
