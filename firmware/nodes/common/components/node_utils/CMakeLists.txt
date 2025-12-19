idf_component_register(
    SRCS "node_utils.c"
    INCLUDE_DIRS "."
    REQUIRES config_storage wifi_manager mqtt_manager json efuse esp_wifi esp_netif esp_event nvs_flash
)
