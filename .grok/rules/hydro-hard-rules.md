# Hydro 2.0 — жёсткие правила для Grok (auto-load)

Полный свод: корневой `GROK.md`. Канон для всех агентов: `AGENTS.md`.  
Спеки: только `doc_ai/`. Локальные: `backend/laravel/docs/AGENTS.md`, `backend/services/AGENTS.md`, `backend/services/automation-engine/AGENT.md`.

## Язык

- Ответы пользователю — **русский**. Код/идентификаторы — английский.

## Нельзя

1. Публиковать MQTT из Laravel или automation-engine (только **history-logger** → MQTT).
2. Ручной DDL — только Laravel-миграции.
3. Ломать пайплайн `ESP32 → MQTT → Python → PG → Laravel → Vue` без миграции всего стека.
4. Integration-тесты AE на `hydro_dev` — только `make test-ae` / `hydro_test`.
5. Hardcoded pH/EC targets; менять auth/roles без нужды; malloc в hot-path firmware.
6. Создавать `.md` документацию без явного запроса (кроме обязательных обновлений контрактов).

## Поток команд

```
Laravel scheduler-dispatch → AE3 (ae3lite) → history-logger POST /commands → MQTT → ESP32
```

Топик: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`

## Перед работой

1. Локальный AGENTS/AGENT в подкаталоге.
2. 2–3 спеки слоя из `doc_ai/`.
3. Backend/Python — Docker; firmware — ESP-IDF (`source /home/georgiy/esp/esp-idf/export.sh`).

## Dev shortcuts

`make up` · `make migrate` · `make seed` · `make test-ae` · `make logs-core` · `make protocol-check`

Хост: `psql -h localhost -U hydro -d hydro_dev -w`, `mosquitto_sub -h localhost -t 'hydro/#' -v`, `http` на :8080/:9000/:9300/:9405.

## При сомнении

Спросить пользователя. Не force-push / reset-db / refresh / prod без подтверждения.
