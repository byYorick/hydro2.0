idf_component_register(
    SRCS "ccs811.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus i2c_cache diagnostics esp_timer
)
