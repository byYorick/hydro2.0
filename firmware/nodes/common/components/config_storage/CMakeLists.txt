idf_component_register(
    SRCS "config_storage.c"
    INCLUDE_DIRS "include"
    REQUIRES nvs_flash
    PRIV_REQUIRES json
)





