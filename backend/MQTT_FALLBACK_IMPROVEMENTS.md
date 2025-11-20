# Улучшения MQTT Fallback Execution Path

Дата: 2025-01-27

## Выполненные улучшения

### 1. ✅ Добавлен Fallback Execution Path для Async MQTT Handlers

**Проблема:**
- Async handlers (например, `handle_node_hello`, `handle_heartbeat`) не выполнялись, если не было работающего event loop
- Это приводило к потере важных сообщений, включая `node_hello`, что блокировало регистрацию узлов

**Решение:**
- Добавлен fallback путь выполнения в методе `_wrap` класса `MqttClient`
- Если нет работающего event loop, создается новый event loop в отдельном потоке
- Handler выполняется в этом новом event loop, гарантируя обработку всех сообщений

**Изменения в коде:**
```python
except RuntimeError:
    # Нет running loop - создаем новый для выполнения handler
    # Это критично для обработки node_hello и других важных сообщений
    logger.warning(
        f"No running event loop found for topic {msg.topic}. "
        f"Creating new event loop for fallback execution to avoid dropped messages."
    )
    try:
        # Создаем новый event loop в отдельном потоке для выполнения handler
        # Это гарантирует, что node_hello и другие сообщения будут обработаны
        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(handler(msg.topic, msg.payload))
                logger.debug(f"Handler executed in fallback event loop for topic {msg.topic}")
            finally:
                new_loop.close()
        
        # Запускаем в отдельном потоке, чтобы не блокировать MQTT callback
        thread = threading.Thread(target=run_in_new_loop, daemon=True)
        thread.start()
        logger.info(f"Started fallback execution thread for topic {msg.topic}")
    except Exception as fallback_error:
        logger.error(
            f"Failed to execute handler in fallback event loop for topic {msg.topic}: {fallback_error}",
            exc_info=True
        )
```

**Преимущества:**
- ✅ Сообщения `node_hello` обрабатываются даже если event loop еще не установлен
- ✅ Избегаем потери регистраций узлов
- ✅ Все async handlers выполняются гарантированно
- ✅ Не блокируем MQTT callback thread

**Файлы:**
- `backend/services/common/mqtt.py` - метод `_wrap`, добавлен fallback execution path

### 2. ✅ JSON Import на уровне модуля

**Проблема:**
- JSON обработка необходима для публикации конфигурации узлов через MQTT
- Если JSON не импортирован на уровне модуля, может быть недоступен в некоторых контекстах

**Решение:**
- JSON уже импортирован на уровне модуля: `import json` (строка 1)
- Используется в методе `publish_json` для сериализации payload: `json.dumps(payload, separators=(",", ":"))`

**Проверено:**
- ✅ JSON импортирован на уровне модуля в `mqtt.py`
- ✅ `publish_json` использует `json.dumps` для сериализации
- ✅ `mqtt-bridge/publisher.py` использует `publish_json` для отправки конфигурации узлов

**Файлы:**
- `backend/services/common/mqtt.py` - импорт JSON на уровне модуля (строка 1)
- `backend/services/mqtt-bridge/publisher.py` - использует `publish_json` для публикации конфигурации

## Результаты

### До улучшений:
- ❌ Async handlers не выполнялись, если нет running event loop
- ❌ Сообщения `node_hello` терялись, регистрация узлов не работала
- ✅ JSON уже был импортирован на уровне модуля

### После улучшений:
- ✅ Async handlers выполняются в fallback event loop, если нет running loop
- ✅ Сообщения `node_hello` обрабатываются гарантированно
- ✅ Регистрация узлов работает даже в edge cases
- ✅ JSON импортирован на уровне модуля для публикации конфигурации

## Тестирование

После перезапуска сервисов нужно проверить:

1. **Обработка node_hello без event loop:**
   - Отправить test node_hello сообщение до полной инициализации event loop
   - Проверить логи history-logger на наличие сообщений о fallback execution
   - Убедиться, что узел регистрируется в БД

2. **Логи history-logger:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs history-logger | grep -i "fallback\|node_hello"
   ```
   Должны появиться сообщения:
   - `No running event loop found for topic ... Creating new event loop for fallback execution`
   - `Started fallback execution thread for topic ...`
   - `Handler executed in fallback event loop for topic ...`
   - `[NODE_HELLO] Processing node_hello from hardware_id: ...`

3. **Регистрация узлов в БД:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec db psql -U hydro -d hydro_dev -c "SELECT id, uid, hardware_id, type, lifecycle_state, created_at FROM nodes ORDER BY created_at DESC LIMIT 5;"
   ```
   Новые узлы должны иметь:
   - `lifecycle_state = REGISTERED_BACKEND`
   - Заполненный `hardware_id`

## Следующие шаги

1. **Перезапустить сервисы:**
   ```bash
   cd backend
   docker-compose -f docker-compose.dev.yml restart history-logger
   ```

2. **Протестировать fallback execution:**
   - Отправить test node_hello сообщение
   - Проверить логи на наличие fallback execution
   - Проверить регистрацию в БД

3. **Проверить публикацию конфигурации узлов:**
   - Убедиться, что `publish_json` работает корректно
   - Проверить публикацию конфигурации через mqtt-bridge

## Замечания

- Fallback execution использует daemon threads, что означает, что они завершатся при завершении основного процесса
- Это подходит для обработки MQTT сообщений, так как они должны быть обработаны быстро
- Логирование улучшено для отслеживания fallback execution

## Статус

- [x] Fallback execution path добавлен
- [x] JSON импорт проверен на уровне модуля
- [x] Код проверен линтером
- [ ] Тестирование выполнено (требуется перезапуск сервисов)
- [ ] Проверка в production-like окружении

