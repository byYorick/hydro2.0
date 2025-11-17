idf_component_register(
    SRCS "connection_status.c"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES wifi_manager mqtt_manager esp_wifi
)

