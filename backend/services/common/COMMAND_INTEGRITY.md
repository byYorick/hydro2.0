# Command Integrity Agent (P0)

## Запрет прямой публикации команд в MQTT

**ВАЖНО**: Все команды из `backend/services/common/*` должны идти через единый оркестратор `command_orchestrator.send_command()`, а НЕ напрямую через `mqtt_client.publish_json()`.

Единый формат команд (без legacy):
```
{"cmd_id","cmd","params","ts","sig"}
```

## Правила

1. **Запрещено** использовать `mqtt_client.publish_json()` для отправки команд с полем `"cmd"` в `backend/services/common/*`
2. **Обязательно** использовать `command_orchestrator.send_command()` для всех команд
3. Все команды должны иметь `cmd_id` и отслеживаться в БД

## Использование

### Правильно ✅

```python
from .command_orchestrator import send_command

# Отправка команды через оркестратор
result = await send_command(
    zone_id=zone_id,
    node_uid=node_uid,
    channel=channel,
    cmd="run_pump",
    params={"duration_ms": 15000},
    wait_for_response=True,  # Опционально: ждать результата
    timeout_sec=30.0
)

if result.get("status") == "sent":
    cmd_id = result["cmd_id"]
    # Команда отправлена, можно отслеживать статус
```

### Неправильно ❌

```python
# ЗАПРЕЩЕНО: прямая публикация в MQTT
payload = {"cmd": "run_pump", "params": {"duration_ms": 15000}}
topic = f"hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command"
mqtt_client.publish_json(topic, payload, qos=1, retain=False)
```

## Преимущества единого оркестратора

1. **Автоматический cmd_id**: каждая команда получает уникальный идентификатор
2. **Отслеживание статусов**: команды записываются в БД со статусами QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED
3. **Ретраи**: оркестратор может повторять неудачные попытки
4. **Мониторинг**: все команды видны в БД и могут быть отслежены
5. **Единый формат**: все команды соответствуют единому контракту

## Проверка нарушений

Для проверки, что ни один модуль не публикует команды напрямую, используйте:

```bash
# Поиск прямых публикаций команд
grep -r "publish_json.*cmd" backend/services/common/ --exclude-dir=test_*
grep -r 'mqtt_client\.publish_json' backend/services/common/ --exclude-dir=test_*
```

В результатах должны быть только тесты (mock'и) и НЕ должно быть реальных вызовов.

## Рефакторинг

Все модули в `backend/services/common/*` были обновлены:
- ✅ `water_flow.py` - все команды через `send_command()`
- ✅ `water_cycle.py` - все команды через `send_command()`

## DoD

✅ Ни один модуль в `backend/services/common/*` не публикует `{"cmd": ...}` в MQTT без `cmd_id` и без трекинга результата

✅ Все команды идут через `command_orchestrator.send_command()`

✅ Все команды имеют `cmd_id` и записываются в БД

✅ Статусы команд отслеживаются: QUEUED → SENT → ACK → DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT (+ SEND_FAILED → SENT)
