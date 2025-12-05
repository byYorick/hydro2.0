# Исправление бага статуса узла (online/offline)

**Дата:** 5 декабря 2025  
**Баг:** Узлы всегда отображаются как "offline" на фронтенде  
**Статус:** ✅ Исправлен

---

## 🐛 Описание бага

### Симптомы:
- ✅ ESP32 отправляет heartbeat каждые 15 секунд
- ✅ History Logger получает и обрабатывает heartbeat
- ✅ `last_heartbeat_at` обновляется в БД
- ✅ `uptime_seconds`, `rssi`, `free_heap_bytes` обновляются
- ❌ **Поле `status` остаётся 'offline'**

### Причина:

**Файл:** `backend/services/history-logger/main.py`, функция `handle_heartbeat()`

**Строки 1246-1260 (ДО исправления):**
```python
# Всегда обновляем timestamp полей
updates.append("last_heartbeat_at=NOW()")
updates.append("updated_at=NOW()")
updates.append("last_seen_at=NOW()")
# ❌ status НЕ обновляется!

# Строим запрос
if len(updates) > 3:
    query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
    await execute(query, *params)
else:
    await execute(
        "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW() WHERE uid=$1",
        # ❌ status НЕ обновляется!
        node_uid
    )
```

**Результат:** 
- История heartbeat записывается
- Метрики (uptime, rssi, free_heap) обновляются
- Но **узел остаётся offline** в UI

---

## ✅ Исправление

**Файл:** `backend/services/history-logger/main.py`

**Изменение:**
```python
# Всегда обновляем timestamp полей и status=online
updates.append("last_heartbeat_at=NOW()")
updates.append("updated_at=NOW()")
updates.append("last_seen_at=NOW()")
updates.append("status='online'")  # ✅ Узел онлайн, если отправляет heartbeat

# Строим запрос
if len(updates) > 4:  # Изменено с 3 на 4 (добавлен status)
    query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
    await execute(query, *params)
else:
    # Только timestamp и status обновления
    await execute(
        "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW(), status='online' WHERE uid=$1",
        # ✅ status обновляется на 'online'
        node_uid
    )
```

**Логика:**
- Узел отправляет heartbeat → значит он **подключён** к WiFi и MQTT
- Поэтому сразу устанавливаем `status = 'online'`

---

## 🧪 Тестирование

### До исправления:
```sql
SELECT uid, status, last_heartbeat_at FROM nodes WHERE uid = 'nd-clim-esp3278e';

      uid        | status  | last_heartbeat_at  
-----------------+---------+--------------------
 nd-clim-esp3278e | offline | 2025-12-05 12:46:46  ← обновляется, но status offline!
```

### После исправления:
```sql
SELECT uid, status, last_heartbeat_at, uptime_seconds, rssi FROM nodes WHERE uid = 'nd-clim-esp3278e';

      uid        | status  | last_heartbeat_at  | uptime_seconds | rssi
-----------------+---------+--------------------+----------------+------
 nd-clim-esp3278e | online  | 2025-12-05 12:49:41 |     66        | -43  ✅
```

**Результат:** ✅ Статус корректно обновляется на 'online'!

---

## 🔄 Механизм работы статуса

### Установка online:
- ✅ Узел отправляет **heartbeat** → History Logger устанавливает `status='online'`
- ✅ Обновляется каждые ~15 секунд (частота отправки heartbeat)

### Определение offline:
**Вариант 1: Laravel Accessor (рекомендуется)**

Добавить accessor в `DeviceNode` модель:
```php
public function getStatusAttribute($value): string
{
    if (!$this->last_heartbeat_at) {
        return 'offline';
    }
    
    // Узел считается offline, если не отправлял heartbeat более 60 секунд
    $threshold = now()->subSeconds(60);
    return $this->last_heartbeat_at->gte($threshold) ? 'online' : 'offline';
}
```

**Вариант 2: Фоновая задача (Laravel Command)**

Создать команду, которая проверяет узлы раз в минуту:
```php
DB::table('nodes')
    ->where('last_heartbeat_at', '<', now()->subSeconds(60))
    ->update(['status' => 'offline']);
```

---

## 📊 Текущий статус

**ESP32 узел `esp32-78e36ddde468`:**
- Hardware ID: `esp32-78e36ddde468`
- UID: `nd-clim-esp3278e`
- Status: **online** ✅
- Last heartbeat: 2025-12-05 12:49:41
- Uptime: 66 секунд
- RSSI: -43 dBm
- Lifecycle: REGISTERED_BACKEND

**Отправляет:**
- ✅ node_hello
- ✅ Temperature telemetry
- ✅ Humidity telemetry  
- ✅ Heartbeat

**Проблемы:**
- ⚠️ Не получил конфиг (валидация отклонила)
- ⚠️ Использует дефолтный node_id из прошивки
- 🔧 Требуется перепрошивка с исправленной валидацией

---

## 🎯 Итог

✅ **Баг статуса исправлен!**
- History Logger теперь устанавливает `status='online'` при получении heartbeat
- Узлы, отправляющие heartbeat, отображаются как online
- На фронтенде статус обновляется корректно

**Проверьте в UI:** http://localhost:8080/devices

Узел `nd-clim-esp3278e` должен отображаться со статусом **online**! 🚀

---

## 📝 Дополнительные улучшения (опционально)

### 1. Автоматический переход в offline

Добавить Laravel команду для фонового мониторинга:

**Файл:** `app/Console/Commands/CheckNodeHeartbeats.php`
```php
public function handle(): int
{
    $threshold = now()->subSeconds(60);
    
    $affectedNodes = DB::table('nodes')
        ->where('status', 'online')
        ->where('last_heartbeat_at', '<', $threshold)
        ->update(['status' => 'offline']);
    
    $this->info("Marked {$affectedNodes} nodes as offline");
    return 0;
}
```

**Запуск каждую минуту:** `routes/console.php`
```php
Schedule::command('nodes:check-heartbeats')->everyMinute();
```

### 2. Real-time обновление на фронтенде

Через WebSocket (Reverb) отправлять события изменения статуса:
- `device.online` - когда приходит heartbeat
- `device.offline` - когда таймаут истёк

Фронтенд автоматически обновит UI без перезагрузки страницы.

