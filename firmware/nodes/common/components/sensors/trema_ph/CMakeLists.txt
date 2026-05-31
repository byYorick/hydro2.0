idf_component_register(
    SRCS "trema_ph.c"
    INCLUDE_DIRS "include"
    REQUIRES i2c_bus i2c_cache freertos
)

# Опционально: отключить программный reset при init (как iarduino _begin+reset), по умолчанию включён в trema_ph.h
# target_compile_definitions(${COMPONENT_LIB} PRIVATE TREMA_PH_INIT_SOFTWARE_RESET=0)

