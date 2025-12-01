idf_component_register(
    SRCS "i2c_cache.c"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES freertos esp_timer esp_system
)

