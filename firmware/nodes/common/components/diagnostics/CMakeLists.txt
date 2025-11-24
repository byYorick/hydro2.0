idf_component_register(
    SRCS "diagnostics.c"
    INCLUDE_DIRS "include"
    REQUIRES 
        node_framework
        mqtt_manager
        wifi_manager
        memory_pool
        i2c_cache
        freertos
        esp_timer
        esp_system
        esp_wifi
        json
)

