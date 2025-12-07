idf_component_register(
    SRCS "heartbeat_task.c"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES mqtt_manager wifi_manager freertos esp_wifi esp_timer esp_system json node_framework memory_pool oled_ui
)
