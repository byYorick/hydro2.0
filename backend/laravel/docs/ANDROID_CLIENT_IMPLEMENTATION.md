# Android-клиент: реализация Zone Event Ledger

## Обзор

Android-клиент должен реализовать надежную синхронизацию состояния зоны через Zone Event Ledger. Это гарантирует, что клиент никогда не потеряет события, даже при переподключении WebSocket или временной недоступности сети.

---

## 1. Хранение last_event_id локально

### Требования

- Сохранять `last_event_id` для каждой зоны локально (SharedPreferences или локальная БД)
- Ключ: `zone_{zone_id}_last_event_id`
- Обновлять при каждом полученном событии из WebSocket
- Использовать для catch-up при переподключении

### Пример реализации

```kotlin
class ZoneEventStorage(private val context: Context) {
    private val prefs = context.getSharedPreferences("zone_events", Context.MODE_PRIVATE)
    
    fun saveLastEventId(zoneId: Int, eventId: Long) {
        prefs.edit()
            .putLong("zone_${zoneId}_last_event_id", eventId)
            .apply()
    }
    
    fun getLastEventId(zoneId: Int): Long? {
        val eventId = prefs.getLong("zone_${zoneId}_last_event_id", -1)
        return if (eventId >= 0) eventId else null
    }
}
```

---

## 2. onResume: snapshot → events after_id → WS subscribe

### Последовательность действий при onResume

1. **Получить snapshot зоны**
   ```kotlin
   GET /api/zones/{zone_id}/snapshot
   ```
   - Ответ содержит `last_event_id` (курсор событий)
   - Обновить локальное состояние из snapshot

2. **Catch-up пропущенных событий**
   ```kotlin
   val localLastEventId = storage.getLastEventId(zoneId)
   val snapshotLastEventId = snapshot.last_event_id
   
   if (localLastEventId != null && localLastEventId < snapshotLastEventId) {
       // Есть пропущенные события - догоняем
       var afterId = localLastEventId
       var hasMore = true
       
       while (hasMore) {
           val response = api.getZoneEvents(zoneId, afterId, limit = 100)
           processEvents(response.data)
           afterId = response.meta.last_event_id
           hasMore = response.meta.has_more
       }
   }
   ```

3. **Подписаться на WebSocket**
   ```kotlin
   websocket.subscribe("hydro.zone.${zoneId}")
   ```

### Полный пример onResume

```kotlin
suspend fun syncZone(zoneId: Int) {
    try {
        // 1. Получаем snapshot
        val snapshot = api.getZoneSnapshot(zoneId)
        updateLocalState(snapshot)
        
        // 2. Catch-up пропущенных событий
        val localLastEventId = storage.getLastEventId(zoneId)
        if (localLastEventId != null && localLastEventId < snapshot.last_event_id) {
            catchUpEvents(zoneId, localLastEventId, snapshot.last_event_id)
        }
        
        // 3. Сохраняем текущий last_event_id из snapshot
        storage.saveLastEventId(zoneId, snapshot.last_event_id)
        
        // 4. Подписываемся на WebSocket
        websocket.subscribe("hydro.zone.${zoneId}")
        
    } catch (e: Exception) {
        Log.e(TAG, "Failed to sync zone $zoneId", e)
        // Обработать ошибку (retry, показать уведомление и т.д.)
    }
}
```

---

## 3. Reconciliation строго по event_id (не по времени)

### Важные правила

❌ **НЕ используйте timestamp для reconciliation!**
- `server_ts` может иметь погрешности
- События могут прийти с задержкой
- Могут быть race conditions

✅ **Используйте только `event_id` для reconciliation!**
- `event_id` монотонно возрастает
- Строгий порядок гарантирован
- Нет пробелов в последовательности

### Пример обработки WebSocket событий

```kotlin
fun handleWebSocketEvent(zoneId: Int, event: ZoneEvent) {
    val localLastEventId = storage.getLastEventId(zoneId)
    
    // Проверяем порядок событий
    if (localLastEventId != null) {
        val expectedNextId = localLastEventId + 1
        
        if (event.event_id > expectedNextId) {
            // Пропущены события - нужно catch-up
            Log.w(TAG, "Event gap detected: expected $expectedNextId, got ${event.event_id}")
            catchUpEvents(zoneId, localLastEventId, event.event_id - 1)
        } else if (event.event_id < expectedNextId) {
            // Старое событие (может быть задержка сети) - игнорируем
            Log.d(TAG, "Ignoring old event: ${event.event_id} < $expectedNextId")
            return
        }
    }
    
    // Обрабатываем событие
    processEvent(event)
    
    // Обновляем last_event_id
    storage.saveLastEventId(zoneId, event.event_id)
}
```

### Обработка gap в событиях

```kotlin
suspend fun catchUpEvents(zoneId: Int, fromEventId: Long, toEventId: Long) {
    var currentId = fromEventId
    var hasMore = true
    
    while (hasMore && currentId < toEventId) {
        val response = api.getZoneEvents(
            zoneId = zoneId,
            afterId = currentId,
            limit = 100
        )
        
        // Обрабатываем события в строгом порядке
        response.data.forEach { event ->
            if (event.id == currentId + 1) {
                processEvent(event)
                currentId = event.id
            } else {
                // Обнаружен разрыв - логируем и продолжаем
                Log.e(TAG, "Unexpected event ID: expected ${currentId + 1}, got ${event.id}")
            }
        }
        
        hasMore = response.meta.has_more
    }
}
```

---

## 4. Типы событий и их обработка

### Command Status Updates

```kotlin
when (event.type) {
    "command_status" -> {
        val commandId = event.payload["commandId"] as String
        val status = event.payload["status"] as String
        updateCommandStatus(commandId, status)
    }
}
```

### Alert Updates

```kotlin
when (event.type) {
    "alert_created" -> {
        val alert = parseAlert(event.payload)
        addAlert(alert)
    }
    "alert_updated" -> {
        val alertId = event.payload["alert_id"] as Int
        updateAlert(alertId, event.payload)
    }
}
```

### Telemetry Updates

**Важно:** Телеметрия может приходить с высокой частотой (каждые 3-5 секунд).
- Для UI используйте debounce/throttle
- Не обновляйте UI на каждое событие
- Агрегируйте обновления (например, раз в секунду)

```kotlin
when (event.type) {
    "telemetry_updated" -> {
        val metricType = event.payload["metric_type"] as String
        val value = event.payload["value"] as Double
        
        // Debounce для UI обновлений
        telemetryUpdateDebouncer.update(metricType, value)
    }
}
```

---

## 5. Обработка ошибок

### Сценарии ошибок

1. **Snapshot недоступен**
   - Retry с экспоненциальной задержкой
   - Использовать последний известный snapshot из кеша (если есть)

2. **Events API недоступен**
   - Не блокировать UI
   - Продолжить с WebSocket подпиской
   - Retry catch-up в фоне

3. **WebSocket разрыв соединения**
   - Автоматически переподключиться
   - При переподключении выполнить catch-up

4. **Большой gap в событиях**
   - Если gap > 1000 событий, показать уведомление пользователю
   - Возможно, проще запросить новый snapshot вместо catch-up

---

## 6. Оптимизация производительности

### Кеширование

- Кешировать snapshot на 1-2 минуты
- Не запрашивать snapshot при каждом onResume, если он свежий

### Batch обработка

- Обрабатывать события батчами при catch-up
- Использовать DiffUtil для RecyclerView при обновлении списков

### Debouncing

- Debounce UI обновлений для телеметрии (100-500ms)
- Не обновлять UI на каждое событие

---

## 7. Тестирование

### Unit тесты

- Тестировать логику reconciliation
- Тестировать обработку gap в событиях
- Тестировать edge cases (null last_event_id, очень большой gap)

### Integration тесты

- Тестировать полный цикл: snapshot → catch-up → WS → reconciliation
- Тестировать обработку разрывов соединения
- Тестировать обработку ошибок API

---

## 8. Чеклист реализации

- [ ] Хранение `last_event_id` локально для каждой зоны
- [ ] Получение snapshot при onResume
- [ ] Catch-up пропущенных событий через Events API
- [ ] Подписка на WebSocket после catch-up
- [ ] Reconciliation по `event_id` (не по времени)
- [ ] Обработка gap в событиях
- [ ] Обработка всех типов событий (command, alert, telemetry, device)
- [ ] Debouncing для телеметрии
- [ ] Обработка ошибок и retry логика
- [ ] Unit и integration тесты

---

## 9. Примеры API вызовов

### Snapshot

```http
GET /api/zones/1/snapshot
Authorization: Bearer {token}

Response:
{
  "status": "ok",
  "data": {
    "snapshot_id": "uuid",
    "server_ts": 1234567890000,
    "last_event_id": 12345,
    "zone_id": 1,
    "devices_online_state": [...],
    "active_alerts": [...],
    "latest_telemetry_per_channel": {...},
    "commands_recent": [...]
  }
}
```

### Events (catch-up)

```http
GET /api/zones/1/events?after_id=12000&limit=100
Authorization: Bearer {token}

Response:
{
  "status": "ok",
  "data": [
    {
      "id": 12001,
      "zone_id": 1,
      "type": "command_status",
      "entity_type": "command",
      "entity_id": "cmd-123",
      "payload_json": {...},
      "server_ts": 1234567890000
    },
    ...
  ],
  "meta": {
    "last_event_id": 12100,
    "has_more": true,
    "count": 100
  }
}
```

---

## 10. Дополнительные рекомендации

1. **Мониторинг**
   - Логировать размер gap при catch-up
   - Метрики: время catch-up, количество событий
   - Алерты при больших gap (>1000 событий)

2. **Безопасность**
   - Не логировать токены и пароли
   - Валидировать все данные из API перед использованием
   - Обрабатывать null/undefined значения безопасно

3. **UX**
   - Показывать индикатор загрузки при catch-up
   - Не блокировать UI на долгое время
   - Предупреждать пользователя при большом gap

