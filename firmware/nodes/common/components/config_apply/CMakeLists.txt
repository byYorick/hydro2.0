idf_component_register(
    SRCS "config_apply.c"
    INCLUDE_DIRS "include"
    REQUIRES config_storage wifi_manager mqtt_manager pump_driver relay_driver freertos json esp_timer
)
