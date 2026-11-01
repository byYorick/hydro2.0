---
name: hydro2-firmware-nodes
description: ESP-IDF ноды Hydro 2.0 (ph/ec/climate/pump/light/relay/storage_irrigation): NodeConfig, common framework, link-loss, E-STOP, каналы. Используй при прошивках firmware/nodes/*, протоколе устройства, OLED/WiFi provisioning, OTA узлов.
type: domain
lifecycle: active
---

# hydro2-firmware-nodes

## Когда применять
Изменения в `firmware/nodes/*`, NodeConfig, channel handlers, E-STOP, link-loss, OTA, coding standards ESP-IDF для Hydro.

## Ноды
`ph_node`, `ec_node`, `climate_node`, `pump_node`, `light_node`, `relay_node`, `storage_irrigation_node` (+ `common`, `test_node`).

## Инварианты Hydro (строже generic embedded)
- Нет `malloc` в hot-path (hard rules).
- E-STOP: пока кнопка активна — актуаторы OFF; ON-команды → `ERROR`/`estop_active`; OFF разрешены (`MQTT_SPEC_FULL.md`).
- Команды с HMAC/ts — см. `hydro2-mqtt-security`.
- Сборка вне Docker: ESP-IDF (`source /home/georgiy/esp/esp-idf/export.sh` per GROK.md).

## Hard rules (defer)
`.grok/rules/hydro-hard-rules.md`; протокол не ломать без миграции стека.

## Override внешних skills
- `embedded-systems` — STM32/generic шаблоны вторичны; hydro запрет malloc hot-path и NodeConfig важнее.
- `esp32-firmware-engineer` — полезен для ESP-IDF/FreeRTOS, но E-STOP/HMAC/каналы — только Hydro docs/code.
- `docker-local-dev` — firmware не в Docker compose core.

## Источники
- `doc_ai/02_HARDWARE_FIRMWARE/{NODE_ARCH_FULL,FIRMWARE_STRUCTURE,NODE_CONFIG_SPEC,NODE_CHANNELS_REFERENCE,ESP32_C_CODING_STANDARDS,NODE_LOGIC_FULL,STORAGE_IRRIGATION_NODE_PROD_SPEC,OTA_UPDATE_PROTOCOL}.md`
- `firmware/nodes/`, `firmware/NODE_CONFIG_SPEC.md`
- `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`
