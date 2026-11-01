idf_component_register(
    SRCS "mqtt_manager.c"
    INCLUDE_DIRS "include"
    REQUIRES mqtt esp_netif esp_event node_utils
    PRIV_REQUIRES esp_timer
)

# Самоподписанный CA для use_tls. Файл не коммитится: скопируйте ca.crt → ca.pem.
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/ca.pem")
    target_add_binary_data(${COMPONENT_LIB} "ca.pem" TEXT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE MQTT_MANAGER_EMBEDDED_CA=1)
endif()

