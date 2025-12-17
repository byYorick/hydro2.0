idf_component_register(
    SRCS 
        "main.c"
        "test_node_app.c"
    INCLUDE_DIRS 
        "."
    REQUIRES 
        node_framework
        mqtt_manager
        heartbeat_task
        config_storage
        node_utils
)

