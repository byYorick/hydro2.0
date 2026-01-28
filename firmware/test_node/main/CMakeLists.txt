idf_component_register(
    SRCS 
        "main.c"
        "test_node_app.c"
    INCLUDE_DIRS 
        "."
    REQUIRES 
        mqtt_manager
        config_storage
        node_utils
        json
        wifi_manager
        freertos
        esp_timer
        esp_system
        esp_wifi
)

