idf_component_register(
    SRCS "logging.c"
    INCLUDE_DIRS "include"
    REQUIRES nvs_flash
    PRIV_REQUIRES esp_timer
)

