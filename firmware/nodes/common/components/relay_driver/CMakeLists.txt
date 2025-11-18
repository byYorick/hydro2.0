idf_component_register(
    SRCS "relay_driver.c"
    INCLUDE_DIRS "include"
    REQUIRES driver json
    PRIV_REQUIRES config_storage
)

