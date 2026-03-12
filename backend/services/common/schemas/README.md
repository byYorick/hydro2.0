# Runtime Schemas (Source Of Truth)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

Этот каталог — **единый источник истины** для runtime JSON-schema в пайплайне
`ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.

## Канонические статусы command_response

Допустимы только:

- `ACK`
- `DONE`
- `ERROR`
- `INVALID`
- `BUSY`
- `NO_EFFECT`
- `TIMEOUT`

Legacy-статусы `ACCEPTED` и `FAILED` не поддерживаются.

## Канонический error payload (`.../error`)

Обязательные поля:

- `level`: `ERROR|WARNING|INFO`
- `component`
- `error_code`
- `message`

`ts` при наличии передаётся как Unix timestamp в миллисекундах.

## Источник и зеркало

- Источник: `backend/services/common/schemas`
- Зеркало: `firmware/schemas`

Синхронизуемые runtime-схемы:

- `command.schema.json`
- `command_response.schema.json`
- `telemetry.schema.json`
- `status.schema.json`
- `heartbeat.schema.json`
- `error.schema.json`
- `error_alert.schema.json`

## Правило именования `error` схем

- `error.schema.json` — каноническая схема payload для MQTT topic `.../error`.
- `error_alert.schema.json` — алиас той же структуры для backend/alerts контекста.
- Эти файлы должны оставаться синхронными.

## Процесс синхронизации

1. Правки делаются только в `backend/services/common/schemas`.
2. После правок запускается:

```bash
./tools/sync_runtime_schemas.sh
```

3. Проверка паритета:

```bash
./tools/check_runtime_schema_parity.sh
```

CI падает при расхождении источника и зеркала.
