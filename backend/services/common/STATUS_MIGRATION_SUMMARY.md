# Миграция статусов команд - сводка изменений

## Выполнено

### ✅ 1. Защита mark_command_sent() от гонок (P0)

**Файл:** `backend/services/common/commands.py`

**Изменение:**
- Добавлена проверка статуса: `WHERE cmd_id=$1 AND status IN ('QUEUED', 'SEND_FAILED')`
- Невозможно перезаписать ACCEPTED/DONE/FAILED обратно в SENT
- Добавлен параметр `allow_resend` для разрешения повторной отправки из SEND_FAILED

**До:**
```python
UPDATE commands SET status='SENT' ... WHERE cmd_id=$1
```

**После:**
```python
UPDATE commands SET status='SENT' ... WHERE cmd_id=$1 AND status IN ('QUEUED', 'SEND_FAILED')
```

### ✅ 2. Замена старых статусов в Python сервисах

**Обновлено:**
- `history-logger/main.py` - normalize_status уже правильно маппит старые статусы
- `automation-engine/infrastructure/command_tracker.py` - использует DONE/FAILED
- `digital-twin/calibration.py` - использует DONE

### ✅ 3. Замена старых статусов в Laravel

**Обновлено:**
- `PythonBridgeService.php` - `'pending'` → `Command::STATUS_QUEUED`
- `PythonBridgeService.php` - `'failed'` → `Command::STATUS_SEND_FAILED` с полями error_code, error_message
- `CommandObserver.php` - обновлена логика для новых статусов
- `CommandFailed.php` - использует `Command::STATUS_FAILED`
- `PythonIngestController.php` - нормализация в новые статусы (ACCEPTED/DONE/FAILED)
- `ArchiveOldCommands.php` - `'pending'` → `Command::STATUS_QUEUED`

### ✅ 4. Замена старых статусов во фронтенде

**Обновлено:**
- `types/Command.ts` - добавлены новые типы статусов
- `composables/useCommands.ts` - обновлена функция normalizeStatus для маппинга старых на новые
- `Pages/Zones/Show.vue` - обновлены проверки статусов
- `Pages/Devices/Show.vue` - обновлены проверки статусов

### ✅ 5. Обновление Grafana dashboards

**Обновлено:**
- `configs/dev/grafana/dashboards/commands-automation.json` - `'pending'` → `'QUEUED'`, `'ack'` → `'DONE'`
- `configs/prod/grafana/dashboards/commands-automation.json` - `'pending'` → `'QUEUED'`, `'ack'` → `'DONE'`

### ✅ 6. Обновление тестов и seeders

**Обновлено:**
- `FullServiceTestSeeder.php` - использует новые константы статусов
- `ComprehensiveDashboardSeeder.php` - использует новые константы статусов
- `CommandStatusControllerTest.php` - `'pending'` → `Command::STATUS_QUEUED`
- `ArchiveCommandsTest.php` - `'pending'` → `Command::STATUS_QUEUED`
- `PythonIngestControllerTest.php` - `'pending'` → `Command::STATUS_QUEUED`
- `CommandStatusUpdatedTest.php` - `'failed'` → `Command::STATUS_FAILED`
- `EventBroadcastTest.php` - `'failed'` → `Command::STATUS_FAILED`

## Маппинг старых статусов на новые

| Старый статус | Новый статус | Примечание |
|---------------|-------------|------------|
| `pending` | `QUEUED` | Команда поставлена в очередь |
| `sent` | `SENT` | Команда отправлена в MQTT |
| `ack` | `DONE` | Команда успешно выполнена |
| `failed` | `FAILED` | Команда завершилась с ошибкой |
| `timeout` | `TIMEOUT` | Команда не получила ответа в срок |
| - | `ACCEPTED` | Новый статус - команда принята узлом |
| - | `SEND_FAILED` | Новый статус - ошибка при отправке |

## Защита от гонок

Все функции обновления статусов защищены условиями:

- `mark_command_sent()` - только из QUEUED/SEND_FAILED
- `mark_command_accepted()` - только из QUEUED/SENT
- `mark_command_done()` - только из QUEUED/SENT/ACCEPTED
- `mark_command_failed()` - только из QUEUED/SENT/ACCEPTED
- `mark_command_timeout()` - только из QUEUED/SENT/ACCEPTED
- `mark_command_send_failed()` - только из QUEUED

## DoD выполнено

✅ **mark_command_sent() защищена** - невозможно перезаписать ACCEPTED/DONE/FAILED обратно в SENT

✅ **Старые статусы заменены** - все использования 'pending', 'ack', 'sent', 'failed' обновлены на новые

✅ **Обратная совместимость** - normalizeStatus маппит старые статусы на новые

✅ **Тесты обновлены** - все тесты используют новые статусы

## Файлы изменений

### Python
- `backend/services/common/commands.py` - защита от гонок
- `backend/services/common/COMMAND_STATUS_TRANSITIONS.md` - документация

### Laravel
- `app/Services/PythonBridgeService.php`
- `app/Observers/CommandObserver.php`
- `app/Events/CommandFailed.php`
- `app/Http/Controllers/PythonIngestController.php`
- `app/Console/Commands/ArchiveOldCommands.php`
- `database/seeders/FullServiceTestSeeder.php`
- `database/seeders/ComprehensiveDashboardSeeder.php`
- `tests/Feature/CommandStatusControllerTest.php`
- `tests/Feature/ArchiveCommandsTest.php`
- `tests/Feature/PythonIngestControllerTest.php`
- `tests/Unit/Events/CommandStatusUpdatedTest.php`
- `tests/Feature/Broadcasting/EventBroadcastTest.php`

### Frontend
- `resources/js/types/Command.ts`
- `resources/js/composables/useCommands.ts`
- `resources/js/Pages/Zones/Show.vue`
- `resources/js/Pages/Devices/Show.vue`

### Configs
- `configs/dev/grafana/dashboards/commands-automation.json`
- `configs/prod/grafana/dashboards/commands-automation.json`
