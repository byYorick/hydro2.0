idf_component_register(
    SRCS "ds18b20.c" "ds18b20_parse.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_timer esp_rom freertos
)
