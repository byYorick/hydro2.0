idf_component_register(
    SRCS "ph_sensor.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus driver adc esp_adc_cal
)

