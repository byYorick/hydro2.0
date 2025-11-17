idf_component_register(
    SRCS "ec_sensor.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus driver
)

