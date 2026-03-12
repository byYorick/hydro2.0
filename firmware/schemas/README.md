# Firmware Schemas (Mirror)

Этот каталог — зеркальная копия runtime-схем из:

`backend/services/common/schemas`

Ручные правки в `firmware/schemas` не допускаются.

## Синхронизация

```bash
./tools/sync_runtime_schemas.sh
```

## Проверка паритета

```bash
./tools/check_runtime_schema_parity.sh
```

При расхождении проверка CI завершится ошибкой.
