idf_component_register(
    SRCS "trema_light.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus i2c_cache
)

