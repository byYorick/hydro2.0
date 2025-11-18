idf_component_register(
    SRCS "pump_driver.c"
    INCLUDE_DIRS "include"
    REQUIRES driver json relay_driver ina209 i2c_bus esp_timer freertos
    PRIV_REQUIRES config_storage
)

