# Changelog — hydro2-mqtt-security

## 0.2.2 — 2026-11-07

- Синхронизированы исправленные PWM, LIGHT_INTENSITY и HMAC fixed-work comparison; сохранены ограничения старых установленных бинарников.

## 0.2.1 — 2026-11-07

- Сверены имя timestamp-константы и включённая граница 10 s.
- Добавлены подтверждённые границы HL validation и PWM/LIGHT/firmware HMAC compatibility.

## 0.2.0 — 2026-11-06

- Метаданные приведены к Agent Skills; добавлена сверка актуальных контрактов и discovery aliases.
- Убраны устаревшие предположения, сохранены ограничения Hydro и пропорциональная проверка.

## 0.1.1 — 2026-11-01

- Исправлен путь к HL: `backend/services/history-logger/command_service.py` (не `commands/`).
- Согласовано состояние MQTT auth с SEC-01/SEC-02: anonymous выключен, TLS включается при наличии сертификатов, доставка node_secret шифруется; ссылка на `README_MQTT_AUTH.md`.
- Убраны trailing spaces (markdown hard-breaks).

## 0.1.0 — 2026-11-01

- Initial release: project skill for Hydro 2.0, grounded in repo `doc_ai/` and code paths.
- Aligns with `.grok/rules/hydro-hard-rules.md` and root `AGENTS.md`.
