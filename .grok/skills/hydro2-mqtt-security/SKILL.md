---
name: hydro2-mqtt-security
description: "MQTT безопасность и топики Hydro 2.0: namespace hydro/{gh}/{zone}/{node}/{channel}/{message_type}, ACL Mosquitto, TLS, node_secret, HMAC команд. Используй при правках протокола, ACL, подписи команд/config, auth узлов или инцидентах invalid_signature/timestamp_expired."
metadata:
  type: domain
  lifecycle: active
  version: "0.2.2"
---

# hydro2-mqtt-security

## Когда применять
Топики, ACL, TLS, `node_secret`, HMAC, ошибки `invalid_signature` / `timestamp_expired` / `invalid_hmac_format`, provisioning секретов.

## Топики
Канон: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
Спеки: `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`, `MQTT_SPEC_FULL.md`.

## HMAC: что канон, что planned
- **Commands HMAC — канон (implemented):** `sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))`; обязательны `ts` и `sig`; skew **≤10s** (`HMAC_TIMESTAMP_TOLERANCE_SEC` / `_MAX_COMMAND_TS_OFFSET_SEC`). Подпись ставит **history-logger**. Firmware: `firmware/nodes/common/components/node_framework/node_command_handler.c`. См. `COMMAND_VALIDATION_ENGINE.md`, `MQTT_SPEC_FULL.md` §7.3, `SECURITY_ARCHITECTURE.md`.
- **Config HMAC — planned / not implemented:** в `SECURITY_ARCHITECTURE.md` явно: verify в `node_config_handler.c` ещё нет; безопасность config-канала пока через ACL + закрытую сеть. Не утверждай, что config HMAC уже работает.

## node_secret
Обязателен, длина ≥ 32. Хранится в NodeConfig. Не логировать и не публиковать в телеметрии.

## ACL / брокер
- Dev и prod: `mosquitto.dev.conf` / `mosquitto.prod.conf` — **`allow_anonymous false`**; пароли и ACL обязательны.
- `mosquitto-entrypoint.sh` добавляет TLS listener 8883 при наличии `server.crt` и `server.key`. Plaintext 1883 отключается через `MQTT_PLAINTEXT_ENABLED=0` после перевода клиентов на TLS.
- Пользователи/ACL: `backend/services/mqtt-bridge/README_MQTT_AUTH.md`, файлы `acl` / `acl.example`. Per-node pattern использует client id = `node_uid`; это не отдельная криптографическая идентичность узла.
- `node_secret` не передаётся plaintext в MQTT NodeConfig: используется `node_secret_enc` (AES-256-GCM); прошивка сохраняет прежний ключ при отсутствии поля или ошибке расшифровки.
- HIL: `infra/hil/mosquitto.acl`; настройки изолированных HIL/e2e проверять отдельно.
- Фактическое включение TLS и параметры установленного стенда проверять по runtime-конфигу; наличие кода не доказывает завершённую миграцию.

## Hard rules (defer)
`.grok/rules/hydro-hard-rules.md`: publish команд только HL→MQTT; ответы пользователю на русском.

## Override внешних skills
- `documentation-guidelines` — не плодить новые `.md` вне обновления контрактов `doc_ai/` / явного запроса; SoT — `hydro2-doc-sot`.
- `embedded-systems` — generic MCU advice не отменяет hydro HMAC/E-STOP/ACL.
- `review-and-ship` — секреты/`node_secret` не коммитить в PR.

## Источники
- `doc_ai/03_TRANSPORT_MQTT/{MQTT_SPEC_FULL,MQTT_NAMESPACE,BACKEND_NODE_CONTRACT_FULL,COMMAND_VALIDATION_ENGINE}.md`
- `doc_ai/08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md`
- `doc_ai/10_AI_DEV_GUIDES/MQTT_TOPICS_SPEC_AI_GUIDE.md`
- `backend/services/history-logger/command_service.py`
- `backend/services/mqtt-bridge/*`

## Актуализация 2026-11-06

- Минимальная telemetry: metric_type/value/ts; node/channel берутся из topic.
- Строгая telemetry JSON Schema и текущий permissive HL ingest имеют разное покрытие: см. MQTT_SPEC_FULL.md §3.2.1. Не объявляй runtime-совместимость по одному паритету зеркал.
- Первичная настройка ESP32: POST /wifi/connect (ssid/password/mqtt_host/mqtt_port), регистрация hydro/node_hello. Android /api/provision пока несовместим с firmware.
- Не печатай secrets, полный NodeConfig, .env или раскрытый Compose config в диагностический отчёт.

## Сверка 2026-11-07

- HL проверяет caps в `history-logger/command_service.py`; он не преобразует PWM `duty` в firmware `value` и не проверяет `timeout_ms` тем же cap, что `duration_ms`.
- AE3 lighting выдаёт `duty` в процентах `0..100`; текущие `climate_node`/`test_node` используют общий `node_pwm_decode`. Legacy `value` сохранён с разными шкалами; старые установленные бинарники требуют обновления.
- Периодическая telemetry `light_node` теперь использует `LIGHT_INTENSITY`; legacy `LIGHT` от старых бинарников мог попасть в историю `OTHER`, которая автоматически не переписывается. Подробности — [MQTT_SPEC_FULL.md](../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md#321-границы-json-schema-и-runtime-ingest).
- Firmware `node_signature_matches` проверяет 64 символа без раннего выхода и не логирует подписи. Не подменяй regression-проверку одним фактом наличия HMAC.
