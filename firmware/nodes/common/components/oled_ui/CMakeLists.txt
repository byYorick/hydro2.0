idf_component_register(
    SRCS "oled_ui.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus driver
)

