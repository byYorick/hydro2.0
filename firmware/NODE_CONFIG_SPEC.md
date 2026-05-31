# NodeConfig — указатель на canonical спецификацию

**Status:** stub / redirect (этот файл больше не содержит самостоятельных правил)
**Дата обновления:** 2026-05-28

## Single source of truth

Полная и канонически актуальная спецификация NodeConfig:

→ [`doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`](../doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md)

Когда правишь NodeConfig, версии, channels, calibration или жизненный цикл — иди в `doc_ai/`, а не сюда.

## Почему этот файл — stub

Ранее этот файл хранил полную копию спецификации и со временем разошёлся с реальным кодом firmware и c canonical документом. Расхождения:

1. Локальная копия утверждала «сервер не отправляет config обратно». Это **неверно** — `firmware/nodes/common/components/node_framework/node_config_handler.c` реально принимает MQTT-push конфига (`.../config`), валидирует, мёрджит, сохраняет в NVS и публикует `config_report` как ACK.
2. В локальной копии отсутствовал `fail_safe_guards` для `irrig`, а пример `storage_irrigation_node` использовал устаревшие `pump_in`/`pump_out` без `level_*`-каналов и guard-параметров.
3. Не было примечания про `climate` auto-add сенсорных каналов.

Чтобы не плодить такой drift, локальная копия удалена. Все runtime/contract-правила NodeConfig живут в `doc_ai/02_HARDWARE_FIRMWARE/`.

## Краткая шпаргалка для firmware-разработчика

Этот раздел — только напоминание. Авторитетные значения — в canonical документе.

- **Версия формата:** `3` (поле `version`)
- **Допустимые `type`:** `ph | ec | climate | irrig | light | relay | water_sensor | recirculation | unknown`
- **Обязательные поля верхнего уровня:** `node_id`, `version`, `type`, `gh_uid`, `zone_uid`, `channels`, `wifi`, `mqtt`
- **MQTT-публикация:** `config_report` на `hydro/{gh}/{zone}/{node}/config_report` после connect + time sync
- **Lifecycle (server-push config):** см. `node_config_handler.c` — валидация → merge с предыдущими критичными секциями (wifi/mqtt/gh_uid/zone_uid/calibration) → `config_storage_save()` → `config_apply_*` → publish нового `config_report` как ACK
- **HMAC config:** timestamp tolerance 60 с (см. `doc_ai/08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md` §2.3.2; status: **planned** — verify-on-node ещё не реализован, см. локальный `node_command_handler.c` для command HMAC 10 с)

## Связанные документы

- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` — canonical
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md` — архитектура нод
- `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md` — структура common-компонентов
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — справочник каналов
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — `config_report` MQTT-контракт
- `firmware/nodes/common/components/node_framework/node_config_handler.c` — реализация runtime lifecycle
- `firmware/nodes/common/components/config_storage/config_storage.c` — NVS persistence
- Шаблоны: `configs/nodes/*.json`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
