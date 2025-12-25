idf_component_register(
    SRCS "log_throttle.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_timer freertos
)
