idf_component_register(
    SRCS "mqtt_manager.c"
    INCLUDE_DIRS "include"
    REQUIRES mqtt esp_netif esp_event
    PRIV_REQUIRES esp_timer
)

