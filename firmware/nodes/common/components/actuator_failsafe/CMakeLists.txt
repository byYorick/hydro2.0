idf_component_register(
    SRCS "actuator_failsafe.c" "actuator_failsafe_logic.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_timer freertos
)
