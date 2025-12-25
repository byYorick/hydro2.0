# PHASE 4 - Команды и двухфазные подтверждения

Дата: 2025-12-25

## ✅ Выполненные задачи

### 4.1 Создана миграция для обновления таблицы `commands`

**Файл:** `2025_12_25_151721_update_commands_for_two_phase_confirmation.php`

**Добавлено:**
- `cycle_id` (FK nullable → grow_cycles) - для связи с циклом выращивания
- `context_type` (enum: cycle|manual|maintenance|calibration) - классификация команд
- `request_id` (string, unique) - для двухфазного подтверждения
- `command_type` (string) - алиас для `cmd` (для единообразия)
- `payload` (jsonb) - алиас для `params` (для единообразия)

**Индексы:**
- `commands_cycle_idx` на `cycle_id`
- `commands_request_id_idx` на `request_id`
- `commands_node_status_idx` на `(node_id, status)`

### 4.2 Создана таблица `command_acks`

**Файл:** `2025_12_25_151722_create_command_acks_table.php`

**Структура:**
- `id` (PK)
- `command_id` (FK → commands)
- `ack_type` (enum: accepted|executed|verified|error)
- `measured_current` (decimal nullable) - измеренный ток
- `measured_flow` (decimal nullable) - измеренный поток
- `error_message` (text nullable) - сообщение об ошибке
- `metadata` (jsonb nullable) - дополнительные данные
- `created_at` (timestamp)

**Индексы:**
- `command_acks_command_type_idx` на `(command_id, ack_type)`
- `command_acks_command_idx` на `command_id`
- `command_acks_type_idx` на `ack_type`

### 4.3 Созданы и обновлены модели

**CommandAck** (`app/Models/CommandAck.php`):
- Модель для подтверждений команд
- Relationships: `command()`
- Scopes: `ofType()`, `successful()`, `errors()`

**Command** (обновлена):
- Добавлены новые поля в `fillable`: `cycle_id`, `context_type`, `request_id`, `command_type`, `payload`
- Добавлены relationships:
  - `cycle()` - BelongsTo GrowCycle
  - `zone()` - BelongsTo Zone
  - `node()` - BelongsTo DeviceNode
  - `acks()` - HasMany CommandAck
  - `lastAck()` - HasOne CommandAck (последнее подтверждение)
- Добавлены scopes:
  - `forCycle()` - команды для цикла
  - `outOfCycle()` - внецикловые команды
  - `withContext()` - команды по типу контекста

## ✅ Acceptance критерии

- ✅ Можно хранить внецикловые команды (cycle_id nullable)
- ✅ Можно отличать accepted vs verified через `ack_type` в `command_acks`
- ✅ Есть `request_id` для двухфазного подтверждения
- ✅ Есть `context_type` для классификации команд (cycle|manual|maintenance|calibration)
- ✅ Поддерживаются измеренные значения (measured_current, measured_flow)
- ✅ Все модели и relationships работают корректно

## 📋 Статус

**PHASE 4 завершена.**

Все компоненты готовы:
- ✅ Миграции созданы и проверены
- ✅ Модели созданы и обновлены
- ✅ Relationships работают корректно
- ✅ Поддержка двухфазного подтверждения реализована

**Следующий шаг:** PHASE 5 - Удаление legacy и финальное ужесточение схемы.

