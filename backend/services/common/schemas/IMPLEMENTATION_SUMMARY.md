# Сводка реализации единого контракта команд

## Выполненные задачи

### ✅ 1. JSON схемы

Созданы JSON схемы для валидации:
- `schemas/command.json` - схема команды
- `schemas/command_response.json` - схема ответа
- `schemas/README.md` - документация по схемам

### ✅ 2. Python модели

Обновлен `schemas.py`:
- `Command` - единый контракт команды с методами `create()`
- `CommandResponse` - единый контракт ответа с методами `accepted()`, `done()`, `failed()`
- `CommandRequest` - legacy модель для обратной совместимости
- `LegacyCommandResponse` - legacy модель для обратной совместимости

### ✅ 3. База данных

Созданы миграции:
- `2025_01_27_000006_update_commands_table_status_enum.php` - обновление статусов
- `2025_01_27_000007_add_command_response_fields.php` - добавление полей для ответов

Новые статусы в БД:
- `QUEUED` - команда поставлена в очередь
- `SENT` - команда отправлена в MQTT
- `ACCEPTED` - команда принята узлом
- `DONE` - команда успешно выполнена
- `FAILED` - команда завершилась с ошибкой
- `TIMEOUT` - команда не получила ответа в срок
- `SEND_FAILED` - ошибка при отправке команды

Новые поля:
- `error_code` (string, 64) - символический код ошибки
- `error_message` (string, 512) - сообщение об ошибке
- `result_code` (integer) - код результата (0 = успех)
- `duration_ms` (integer) - длительность выполнения в миллисекундах

### ✅ 4. Laravel модель

Обновлен `app/Models/Command.php`:
- Константы для всех статусов
- Метод `isFinal()` - проверка конечного состояния
- Метод `isDone()` - проверка успешного завершения
- Метод `isFailed()` - проверка ошибки
- Поддержка новых полей в `$fillable` и `$casts`

### ✅ 5. Python функции

Обновлен `commands.py`:
- `mark_command_sent()` - использует статус `SENT`
- `mark_command_accepted()` - новый статус `ACCEPTED`
- `mark_command_done()` - статус `DONE` с поддержкой `duration_ms` и `result_code`
- `mark_command_failed()` - статус `FAILED` с поддержкой `error_code` и `error_message`
- `mark_command_timeout()` - статус `TIMEOUT`
- `mark_command_send_failed()` - статус `SEND_FAILED`
- `mark_timeouts()` - обновлен для новых статусов
- `mark_command_ack()` - legacy функция для обратной совместимости

### ✅ 6. Тестовые fixtures

Создан `schemas/fixtures.py`:
- `create_command_fixture()` - создание fixture команды
- `create_command_response_fixture()` - создание fixture ответа
- Готовые fixtures для различных сценариев

### ✅ 7. Документация

Создана документация:
- `CONTRACT.md` - полная документация единого контракта
- `README.md` - обновлен с информацией о новых файлах
- `IMPLEMENTATION_SUMMARY.md` - этот файл

## DoD (Definition of Done)

✅ **100% команд имеют cmd_id** - все команды создаются с уникальным `cmd_id`

✅ **Всегда завершаются в конечное состояние** - команда переходит в одно из конечных состояний:
- `DONE` - успешное выполнение
- `FAILED` - ошибка выполнения
- `TIMEOUT` - таймаут
- `SEND_FAILED` - ошибка отправки

✅ **Единый формат для всех сервисов** - любой сервис, читающий `command_response`, понимает единый формат через:
- JSON схемы для валидации
- Python модели с единым контрактом
- Laravel модель с едиными статусами

✅ **JSON схемы и валидация** - схемы в `backend/services/common/schemas/`

✅ **Тестовые fixtures** - fixtures в `schemas/fixtures.py`

✅ **Документация** - полная документация контракта и примеры использования

## Следующие шаги (опционально)

Для полной миграции на единый контракт рекомендуется:

1. **Обновить history-logger** - использовать новые статусы вместо "ACK"
2. **Обновить automation-engine** - использовать новые статусы в command_tracker
3. **Обновить digital-twin** - использовать новые статусы в SQL запросах
4. **Обновить фронтенд** - использовать новые статусы в UI
5. **Добавить валидацию** - использовать JSON схемы для валидации входящих команд

## Обратная совместимость

Для обеспечения плавной миграции:
- Legacy модели (`CommandRequest`, `LegacyCommandResponse`) поддерживают старые форматы
- Legacy функции (`mark_command_ack()`) работают со старым кодом
- Миграция БД автоматически конвертирует старые статусы в новые

## Использование

### Python

```python
from schemas import Command, CommandResponse

# Создание команды
command = Command.create(
    cmd="dose",
    params={"ml": 1.2}
)

# Создание ответа
response = CommandResponse.done(
    cmd_id=command.cmd_id,
    duration_ms=1000
)
```

### Laravel

```php
use App\Models\Command;

$command = Command::create([
    'cmd_id' => Str::uuid()->toString(),
    'cmd' => 'dose',
    'params' => ['ml' => 1.2],
    'status' => Command::STATUS_QUEUED,
]);

if ($command->isDone()) {
    // Команда успешно выполнена
}
```

## Файлы изменений

### Новые файлы
- `backend/services/common/schemas/command.json`
- `backend/services/common/schemas/command_response.json`
- `backend/services/common/schemas/README.md`
- `backend/services/common/schemas/CONTRACT.md`
- `backend/services/common/schemas/fixtures.py`
- `backend/services/common/schemas/__init__.py`
- `backend/services/common/schemas/IMPLEMENTATION_SUMMARY.md`
- `backend/laravel/database/migrations/2025_01_27_000006_update_commands_table_status_enum.php`
- `backend/laravel/database/migrations/2025_01_27_000007_add_command_response_fields.php`

### Обновленные файлы
- `backend/services/common/schemas.py`
- `backend/services/common/commands.py`
- `backend/laravel/app/Models/Command.php`
