idf_component_register(
    SRCS "factory_reset_button.c"
    INCLUDE_DIRS "include"
    REQUIRES nvs_flash esp_system driver freertos
    PRIV_REQUIRES log
)
