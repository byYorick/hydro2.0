# Исправления WebSocket и Rate Limiting

## Проблемы

### 1. WebSocket пытается использовать wss:// вместо ws://
**Ошибка:** `Firefox не может установить соединение с сервером wss://localhost:6001`

**Причина:** Pusher автоматически пытается использовать wss:// даже когда `forceTLS=false`

**Решение:** Явно указан `enabledTransports: useTLS ? ['wss'] : ['ws']` для использования только ws в dev режиме

### 2. Rate Limiting (429 Too Many Requests)
**Ошибка:** Множественные запросы к `/api/system/health` вызывают ошибку 429

**Причина:** 
- Несколько компонентов (HeaderStatusBar, SystemMonitoringModal, Dashboard) одновременно запрашивают health
- Интервал проверки 30 секунд слишком частый для множественных компонентов
- Rate limit 120 запросов/минуту недостаточен

**Решение:**
- Увеличен rate limit до 300 запросов/минуту
- Увеличен интервал проверки с 30 до 60 секунд
- Добавлен глобальный singleton для предотвращения одновременных запросов
- Добавлена задержка для распределения нагрузки между компонентами

## Исправления

### 1. WebSocket конфигурация

**Файл:** `backend/laravel/resources/js/bootstrap.js`

```javascript
enabledTransports: useTLS ? ['wss'] : ['ws'], // Явно указываем только ws для dev
```

### 2. Rate Limiting

**Файл:** `backend/laravel/routes/api.php`

```php
Route::get('system/health', [SystemController::class, 'health'])->middleware('throttle:300,1');
```

### 3. Глобальный singleton для health checks

**Файл:** `backend/laravel/resources/js/composables/useSystemStatus.ts`

- Добавлен глобальный флаг `globalHealthCheckInProgress`
- Множественные компоненты используют один запрос
- Задержка для распределения нагрузки между компонентами

### 4. Увеличены интервалы проверки

- `POLL_INTERVAL`: 30 → 60 секунд
- `WS_CHECK_INTERVAL`: 5 → 10 секунд

## Результат

1. ✅ WebSocket использует правильный протокол (ws:// вместо wss://)
2. ✅ Rate limiting больше не срабатывает
3. ✅ Множественные компоненты не создают дублирующие запросы
4. ✅ Снижена нагрузка на сервер

## Проверка

После применения исправлений:

1. Перезагрузите страницу в браузере
2. Проверьте консоль - не должно быть ошибок wss://
3. Проверьте Network tab - не должно быть ошибок 429
4. WebSocket должен подключаться через ws://localhost:6001

---

_Обновлено: 2024-11-24_





