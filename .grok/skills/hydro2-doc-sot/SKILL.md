---
name: hydro2-doc-sot
description: Работа с doc_ai/ как SoT защищённых контрактов Hydro 2.0; code = SoT runtime. Используй перед фичами/рефакторингом контрактов MQTT/HL/AE3/схемы, при drift docs↔code, выборе INDEX/слоя 01–13, спорах «что канон».
type: meta
lifecycle: active
---

# hydro2-doc-sot

## Формула SoT
1. **Поведение runtime — код** (`code = SoT`).
2. Защищённые контракты (MQTT, команды, схема БД, HL API, AE3 ingress/FSM, retention) — canonical в `doc_ai/`; обязаны совпадать с кодом. Drift → правим docs **или** явно чиним код.
3. Doc-first — **только** для этих контрактов, не для любой фичи.
4. Папка `docs/` удалена; материалы в `doc_ai/`.

## Hard rules (defer)
`.grok/rules/hydro-hard-rules.md`, `AGENTS.md`, `doc_ai/DEV_CONVENTIONS.md`.
Не создавать `.md` без явного запроса (кроме обязательных обновлений контрактов).

## Override внешних skills
- **`documentation-guidelines`** — внешний провоцирует создавать/консолидировать docs широко; в Hydro: только `doc_ai/` контракты + явный запрос. Этот skill **побеждает** documentation-guidelines.
- `docker-local-dev` — не документируй/не поднимай optional сервисы как default.
- `review-and-ship` — Compatible-With строка при смене протокола/данных.

## Навигация
Старт: `doc_ai/INDEX.md`, `SYSTEM_ARCH_FULL.md`, `ARCHITECTURE_FLOWS.md`, `DEV_CONVENTIONS.md`.
Слои: `01_SYSTEM` … `13_TESTING` (+ Android `12_`, AI guides `10_`).

## Источники
- `doc_ai/{INDEX,DEV_CONVENTIONS,SYSTEM_ARCH_FULL,ARCHITECTURE_FLOWS,README_STRUCTURE}.md`
- `AGENTS.md`, `GROK.md`, `.grok/rules/hydro-hard-rules.md`
