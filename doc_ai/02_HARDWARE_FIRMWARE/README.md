# 02_HARDWARE_FIRMWARE — Железо и прошивки

Этот раздел содержит документацию по аппаратной части и прошивкам узлов ESP32.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 📋 Документы раздела

### Основные документы

#### [NODE_ARCH_FULL.md](NODE_ARCH_FULL.md)
**Полная архитектура узлов ESP32**
- Цели и принципы архитектуры
- Структура прошивки
- Жизненный цикл узла
- NodeConfig
- Каналы узла (SensorChannel, ActuatorChannel)
- Telemetry и команды

#### [NODE_CHANNELS_REFERENCE.md](NODE_CHANNELS_REFERENCE.md)
**Справочник каналов узлов**
- Типы каналов (SENSOR, ACTUATOR, VIRTUAL)
- Сенсорные каналы (pH, EC, температура, влажность)
- Разделение domain-ключей и firmware channel id
- Актуаторные каналы (насосы, клапаны, свет)
- Форматы payload

#### [NODE_CONFIG_SPEC.md](NODE_CONFIG_SPEC.md)
**Спецификация NodeConfig**
- Структура JSON конфигурации
- Поля конфигурации для каждого типа ноды
- Валидация конфигурации
- Процесс загрузки и применения

#### [FIRMWARE_STRUCTURE.md](FIRMWARE_STRUCTURE.md)
**Структура прошивки**
- Организация кода
- Модули и компоненты
- Общие библиотеки

#### [HARDWARE_ARCH_FULL.md](HARDWARE_ARCH_FULL.md)
**Аппаратная архитектура**
- Схемы подключения
- Датчики и актуаторы
- Интерфейсы (I2C, SPI, UART)

### Специализированные документы

#### [NODE_LOGIC_FULL.md](NODE_LOGIC_FULL.md)
Логика работы узлов

#### [NODE_OLED_UI_SPEC.md](NODE_OLED_UI_SPEC.md)
Спецификация OLED интерфейса

#### [NODE_INPUT_CONTROLS.md](NODE_INPUT_CONTROLS.md)
Управление через кнопки/энкодеры

#### [NODE_DIAGNOSTICS_ENGINE.md](NODE_DIAGNOSTICS_ENGINE.md)
Диагностика и мониторинг узлов

#### [DEVICE_NODE_PROTOCOL.md](DEVICE_NODE_PROTOCOL.md)
Протокол взаимодействия с узлами

#### [TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md](TEST_NODE_REAL_HW_PROD_READINESS_SPEC.md)
Спецификация `firmware/test_node` для HIL/E2E и доведения реальных нод до production-ready режима:
- фактические каналы и топики;
- режимы (`configured`/`preconfig`, sensor mode);
- ограничения runtime и чек-лист для боевого rollout.

#### [TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md](TEST_NODE_TO_REAL_NODES_MAPPING_MATRIX.md)
Матрица соответствия `test_node` и боевых прошивок:
- сопоставление каналов `test -> real`;
- сопоставление команд `test -> real`;
- обязательные адаптеры/алиасы перед production rollout.

### Wi‑Fi и подключение

#### [WIFI_CONNECTIVITY_ENGINE.md](WIFI_CONNECTIVITY_ENGINE.md)
Движок подключения Wi‑Fi

#### [WIFI_PROVISIONING_FIRST_RUN.md](WIFI_PROVISIONING_FIRST_RUN.md)
Первичная настройка Wi‑Fi

### Обновления

#### [OTA_UPDATE_PROTOCOL.md](OTA_UPDATE_PROTOCOL.md)
Протокол OTA-обновлений

### Конфигурация

#### [SDKCONFIG_PROFILES.md](SDKCONFIG_PROFILES.md)
Профили конфигурации ESP-IDF

### Стандарты кодирования

#### [ESP32_C_CODING_STANDARDS.md](ESP32_C_CODING_STANDARDS.md)
Стандарты кодирования для ESP32

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[03_TRANSPORT_MQTT](../03_TRANSPORT_MQTT/)** — MQTT протокол
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend интеграция

---

## 🎯 С чего начать

1. **Разработка новой ноды?** → Начните с [NODE_ARCH_FULL.md](NODE_ARCH_FULL.md)
2. **Нужны каналы?** → Изучите [NODE_CHANNELS_REFERENCE.md](NODE_CHANNELS_REFERENCE.md)
3. **Работа с конфигурацией?** → См. [NODE_CONFIG_SPEC.md](NODE_CONFIG_SPEC.md)
4. **Структура кода?** → Прочитайте [FIRMWARE_STRUCTURE.md](FIRMWARE_STRUCTURE.md)

---

**См. также:** [Главный индекс документации](../INDEX.md)
