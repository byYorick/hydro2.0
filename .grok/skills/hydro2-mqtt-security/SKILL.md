---
name: hydro2-mqtt-security
description: MQTT безопасность и топики Hydro 2.0: namespace hydro/{gh}/{zone}/{node}/{channel}/{message_type}, ACL Mosquitto, TLS, node_secret, HMAC команд. Используй при правках протокола, ACL, подписи команд/config, auth узлов или инцидентах invalid_signature/timestamp_expired.
type: domain
lifecycle: active
---

# hydro2-mqtt-security

## Когда применять
Топики, ACL, TLS, `node_secret`, HMAC, ошибки `invalid_signature` / `timestamp_expired` / `invalid_hmac_format`, provisioning секретов.

## Топики
Канон: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`  
Спеки: `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`, `MQTT_SPEC_FULL.md`.

## HMAC: что канон, что planned
- **Commands HMAC — канон (implemented):** `sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))`; обязательны `ts` и `sig`; skew **10s** (`HMAC_TIMESTAMP_TOLERANCE_SEC` / `_MAX_TIMESTAMP_SKEW_SEC`). Подпись ставит **history-logger**. Firmware: `firmware/nodes/common/components/node_framework/node_command_handler.c`. См. `COMMAND_VALIDATION_ENGINE.md`, `MQTT_SPEC_FULL.md` §7.3, `SECURITY_ARCHITECTURE.md`.
- **Config HMAC — planned / not implemented:** в `SECURITY_ARCHITECTURE.md` явно: verify в `node_config_handler.c` ещё нет; безопасность config-канала пока через ACL + закрытую сеть. Не утверждай, что config HMAC уже работает.

## node_secret
Обязателен, длина ≥ 32. Хранится в NodeConfig. Не логировать и не публиковать в телеметрии.

## ACL / брокер
Примеры и prod/dev: `backend/services/mqtt-bridge/acl`, `acl.example`, `mosquitto.dev.conf`, `mosquitto.prod.conf`; HIL: `infra/hil/mosquitto.acl`.

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
- `backend/services/history-logger/commands/command_service.py`
- `backend/services/mqtt-bridge/*`
