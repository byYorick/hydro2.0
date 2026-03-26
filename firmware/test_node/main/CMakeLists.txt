idf_component_register(
    SRCS 
        "main.c"
        "test_node_app.c"
        "test_node_ui.c"
    INCLUDE_DIRS 
        "."
    REQUIRES 
        mqtt_manager
        config_storage
        setup_portal
        node_utils
        json
        wifi_manager
        freertos
        esp_timer
        esp_system
        esp_wifi
        driver
        esp_lcd
        esp_lcd_ili9341
        lvgl
)

# LVGL 9.2.0 emits -Wtype-limits when circle cache is explicitly disabled
# with CONFIG_LV_DRAW_SW_CIRCLE_CACHE_SIZE=0. Suppress it only for vendor code.
idf_component_get_property(lvgl_lib lvgl__lvgl COMPONENT_LIB)
target_compile_options(${lvgl_lib} PRIVATE -Wno-type-limits)
