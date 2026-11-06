# Железо и прошивки

**Статус:** навигационный guide.

ESP32, NodeConfig, каналы, диагностика, сеть и аппаратные справочники.

## Документы

- [CONFIG_REPORT_HANDLING.md](CONFIG_REPORT_HANDLING.md) — Обработка config_report от ноды
- [DEVICE_NODE_PROTOCOL.md](DEVICE_NODE_PROTOCOL.md) — Полная спецификация протокола узлов ESP32 (2.0)
- [ESP32_C_CODING_STANDARDS.md](ESP32_C_CODING_STANDARDS.md) — Стандарты написания прошивки на C под ESP32 (ESP-IDF)
- [FIRMWARE_STRUCTURE.md](FIRMWARE_STRUCTURE.md) — Полная структура прошивки 2.0 для ESP32
- [HARDWARE_ARCH_FULL.md](HARDWARE_ARCH_FULL.md) — Полная аппаратная архитектура системы 2.0 (узлы, сенсоры, питание, защита, топология)
- [NODE_ARCH_FULL.md](NODE_ARCH_FULL.md) — Полная архитектура узлов ESP32 2.0 (Детальный документ)
- [NODE_CHANNELS_REFERENCE.md](NODE_CHANNELS_REFERENCE.md) — Полный справочник каналов узлов 2.0 (ESP32)
- [NODE_CONFIG_SPEC.md](NODE_CONFIG_SPEC.md) — Спецификация NodeConfig для ESP32-нод
- [NODE_DIAGNOSTICS_ENGINE.md](NODE_DIAGNOSTICS_ENGINE.md) — Полный движок диагностики узлов ESP32 в системе 2.0
- [NODE_INPUT_CONTROLS.md](NODE_INPUT_CONTROLS.md) — Абстракция локального ввода на узле
- [NODE_LOGIC_FULL.md](NODE_LOGIC_FULL.md) — Полная логика работы узлов ESP32 2.0 (детальный документ)
- [NODE_OLED_UI_SPEC.md](NODE_OLED_UI_SPEC.md) — Спецификация локального UI на OLED 128×64 для узлов ESP32
- [OTA_UPDATE_PROTOCOL.md](OTA_UPDATE_PROTOCOL.md) — Полная спецификация OTA-обновления узлов ESP32 для системы 2.0
- [SDKCONFIG_PROFILES.md](SDKCONFIG_PROFILES.md) — Профили sdkconfig для узлов 2.0
- [STORAGE_IRRIGATION_NODE_PROD_SPEC.md](STORAGE_IRRIGATION_NODE_PROD_SPEC.md) — Production-спецификация ноды накопления и полива (`storage_irrigation_node`)
- [TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md](TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md) — Спецификация test_node для доведения реальных нод до боевого режима
- [TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md](TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md) — Матрица соответствия `firmware/test_node` и боевых прошивок нод
- [WIFI_CONNECTIVITY_ENGINE.md](WIFI_CONNECTIVITY_ENGINE.md) — Wi-Fi connectivity runtime для ESP32-нод (2.0)
- [WIFI_PROVISIONING_FIRST_RUN.md](WIFI_PROVISIONING_FIRST_RUN.md) — Первичная настройка Wi-Fi узла

Нормативные контракты сверяются с текущим кодом по правилам `AGENTS.md`.
[Главный индекс](../INDEX.md).
