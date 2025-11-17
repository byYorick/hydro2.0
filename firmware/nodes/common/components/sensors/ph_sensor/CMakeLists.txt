idf_component_register(
    SRCS "ph_sensor.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus driver esp_adc
    PRIV_REQUIRES config_storage json
)

