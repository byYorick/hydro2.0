idf_component_register(
    SRCS "dose_limit_node.c"
    INCLUDE_DIRS "include"
    REQUIRES dose_limit config_storage nvs_flash json freertos node_framework
)
