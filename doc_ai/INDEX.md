# Индекс документации Hydro 2.0

**Версия:** 2.8
**Дата обновления:** 2026-11-09

## Начало работы

1. [SYSTEM_ARCH_FULL.md](SYSTEM_ARCH_FULL.md) — обзор системы и границы компонентов.
2. [ARCHITECTURE_FLOWS.md](ARCHITECTURE_FLOWS.md) — потоки команд, телеметрии и инварианты AE3.
3. [DEV_CONVENTIONS.md](DEV_CONVENTIONS.md) — конвенции, источники истины и проверки.
4. [README_STRUCTURE.md](README_STRUCTURE.md) — устройство текущего каталога.

Правила агента — корневой `AGENTS.md`. Runtime определяется кодом; защищённые
контракты в `doc_ai/` должны совпадать с реализацией. Документ может быть
`canonical` (контракт) или `guide` (руководство/справочник); guide не переопределяет контракт.

Работа агента задаётся поручением пользователя. В документации нет самостоятельной
очереди незавершённых этапов. История удалённых планов и промежуточных отчётов
доступна в Git.

## Разделы

| Раздел | Содержание |
|---|---|
| [01_SYSTEM](01_SYSTEM/README.md) | Доменная модель, dataflow, lifecycle/bind/detach нод |
| [02_HARDWARE_FIRMWARE](02_HARDWARE_FIRMWARE/README.md) | ESP32, аппаратная часть, NodeConfig, Wi-Fi, диагностика |
| [03_TRANSPORT_MQTT](03_TRANSPORT_MQTT/README.md) | Namespace, payload, command validation |
| [04_BACKEND_CORE](04_BACKEND_CORE/README.md) | Laravel, AE3, HL API, authority, read-model, суточный контур |
| [05_DATA_AND_STORAGE](05_DATA_AND_STORAGE/README.md) | Модели, телеметрия, retention |
| [06_DOMAIN_ZONES_RECIPES](06_DOMAIN_ZONES_RECIPES/README.md) | Рецепты, PID, correction, полив/свет/климат |
| [07_FRONTEND](07_FRONTEND/README.md) | Inertia/Vue, роли, API и тестирование UI |
| [08_SECURITY_AND_OPS](08_SECURITY_AND_OPS/README.md) | Безопасность, эксплуатация, мониторинг и восстановление |
| [09_AI_AND_DIGITAL_TWIN](09_AI_AND_DIGITAL_TWIN/README.md) | Текущие опциональные компоненты и ограничения |
| [10_AI_DEV_GUIDES](10_AI_DEV_GUIDES/README.md) | Работа с ИИ и проектные skills |
| [12_ANDROID_APP](12_ANDROID_APP/README.md) | Android-клиент, API и ограничения provisioning |
| [13_TESTING](13_TESTING/README.md) | Python E2E, realhw, Playwright и диагностика тестов |
| [14_GROWING_REFERENCE](14_GROWING_REFERENCE/README.md) | Агрономические и аппаратные справочники выращивания |
| [adr](adr/README.md) | Архитектурные решения (`proposed`): перечень систем, общий бак, failsafe канала, MQTT prod |

## Защищённые контракты

- [MQTT_SPEC_FULL.md](03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md) и [MQTT_NAMESPACE.md](03_TRANSPORT_MQTT/MQTT_NAMESPACE.md) — wire-протокол и топики.
- [BACKEND_NODE_CONTRACT_FULL.md](03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md) — backend↔node.
- [CONFIG_REPORT_HANDLING.md](02_HARDWARE_FIRMWARE/CONFIG_REPORT_HANDLING.md) — наблюдение wire ACK конфигурации.
- [ae3lite.md](04_BACKEND_CORE/ae3lite.md) — ingress, execution, single-writer и recovery.
- [HISTORY_LOGGER_API.md](04_BACKEND_CORE/HISTORY_LOGGER_API.md) — публикация и ingest.
- [AUTOMATION_CONFIG_AUTHORITY.md](04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — authority/config bundles.
- [LARAVEL_AE3_READ_MODEL_CONTRACT.md](04_BACKEND_CORE/LARAVEL_AE3_READ_MODEL_CONTRACT.md) — контракт прямого SQL read-model.
- [DATA_MODEL_REFERENCE.md](05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md) и [DATA_RETENTION_POLICY.md](05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md).
- [CORRECTION_CYCLE_SPEC.md](06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md) и [EFFECTIVE_TARGETS_SPEC.md](06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md).
- [GREENHOUSE_CLIMATE_CONTROL_SPEC.md](06_DOMAIN_ZONES_RECIPES/GREENHOUSE_CLIMATE_CONTROL_SPEC.md) — действующий климатический контур теплицы.

## Практические точки входа

- [Архитектурные решения](adr/README.md) — ADR-0001…0004 (`proposed`, не runtime и не замена контрактов слоя).
- [Сводка реализации](IMPLEMENTATION_STATUS.md) — состояние репозитория; не акт приёмки стенда.
- [Суточный контур](04_BACKEND_CORE/CROP_DAY_RUNTIME.md) — существующие crop-day функции и их владельцы.
- [REST API](04_BACKEND_CORE/REST_API_REFERENCE.md) — endpoint-ы и авторизация.
- [WebSocket/Reverb](11_WEBSOCKET_ARCHITECTURE.md) — realtime UI.
- [Backup/recovery](08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md) и [runbooks](08_SECURITY_AND_OPS/RUNBOOKS.md).
- [Проектные skills](10_AI_DEV_GUIDES/PROJECT_SKILLS.md) — каталог, источники и offline-проверка.
- [Realhw test_node](13_TESTING/REALHW_TEST_NODE_AGENT_GUIDE.md) — MQTT 1884, отдельный контур.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
