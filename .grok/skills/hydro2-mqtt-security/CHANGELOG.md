# Changelog — hydro2-mqtt-security

## 0.1.1 — 2026-11-01

- Исправлен путь к HL: `backend/services/history-logger/command_service.py` (не `commands/`).
- Согласовано состояние MQTT auth с SEC-01/SEC-02: anonymous выключен, TLS включается при наличии сертификатов, доставка node_secret шифруется; ссылка на `README_MQTT_AUTH.md`.
- Убраны trailing spaces (markdown hard-breaks).

## 0.1.0 — 2026-11-01

- Initial release: project skill for Hydro 2.0, grounded in repo `doc_ai/` and code paths.
- Aligns with `.grok/rules/hydro-hard-rules.md` and root `AGENTS.md`.
