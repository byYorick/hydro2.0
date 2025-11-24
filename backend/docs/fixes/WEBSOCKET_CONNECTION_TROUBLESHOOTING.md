# Диагностика проблем с WebSocket подключением

## Симптомы

- WebSocket показывает статус "Отключено"
- Сообщение "Соединение разорвано"
- Real-time обновления не работают

## Шаги диагностики

### 1. Проверка Reverb сервера

```bash
# Проверить, запущен ли Reverb
docker exec backend-laravel-1 ps aux | grep reverb

# Проверить, слушает ли порт 6001
docker exec backend-laravel-1 netstat -tuln | grep 6001

# Проверить логи Reverb
docker exec backend-laravel-1 tail -50 /tmp/reverb.log
```

### 2. Проверка конфигурации

```bash
# Проверить переменные окружения
docker exec backend-laravel-1 env | grep -E "REVERB_|VITE_REVERB|VITE_PUSHER|VITE_ENABLE_WS" | sort
```

Должны быть установлены:
- `REVERB_APP_KEY=local` (или другое значение)
- `REVERB_PORT=6001`
- `VITE_ENABLE_WS=true`
- `VITE_REVERB_APP_KEY=local` (должно совпадать с REVERB_APP_KEY)
- `VITE_REVERB_HOST=localhost`
- `VITE_REVERB_PORT=6001`

### 3. Проверка в браузере

Откройте консоль браузера (F12) и проверьте:

1. **Инициализация Echo:**
   ```
   [bootstrap.js] Инициализация Echo: { wsHost: "localhost", wsPort: 6001, ... }
   [bootstrap.js] Echo инициализирован успешно
   ```

2. **Статус подключения через 2 секунды:**
   ```
   [WebSocket] Connection status after 2s: { state: "connected", ... }
   ```

3. **Ошибки подключения:**
   - Если видите `[WebSocket] Connection error:` - проверьте доступность порта
   - Если видите `[WebSocket] Connection not established` - проверьте конфигурацию

### 4. Проверка порта

Убедитесь, что порт 6001 проброшен в `docker-compose.dev.yml`:
```yaml
ports:
  - "6001:6001"
```

### 5. Проверка аутентификации

Проверьте, что маршрут `/broadcasting/auth` работает:
```bash
curl -X POST http://localhost:8080/broadcasting/auth \
  -H "Cookie: $(docker exec backend-laravel-1 cat /tmp/session_cookie 2>/dev/null || echo '')" \
  -H "Content-Type: application/json" \
  -d '{"socket_id":"test","channel_name":"private-test"}'
```

### 6. Перезапуск Reverb

Если Reverb не запущен или работает некорректно:

```bash
# Перезапустить контейнер Laravel
docker-compose restart laravel

# Или перезапустить только Reverb через supervisor
docker exec backend-laravel-1 supervisorctl restart reverb
```

### 7. Проверка CORS и сетевых настроек

Если подключение не устанавливается, проверьте:

1. **Блокировку порта файрволом:**
   ```bash
   sudo ufw status | grep 6001
   ```

2. **Доступность порта из браузера:**
   - Откройте `http://localhost:6001/app/local` в браузере
   - Должен вернуться ответ (не обязательно успешный, но не "Connection refused")

### 8. Логирование в реальном времени

Следите за логами в реальном времени:
```bash
# Логи Laravel
docker logs backend-laravel-1 -f 2>&1 | grep -i "websocket\|reverb\|echo"

# Логи Reverb
docker exec backend-laravel-1 tail -f /tmp/reverb.log
```

## Частые проблемы и решения

### Проблема: Reverb не запускается

**Решение:**
1. Проверьте логи: `docker exec backend-laravel-1 tail -50 /tmp/reverb.log`
2. Проверьте конфигурацию: `docker exec backend-laravel-1 php artisan config:show reverb`
3. Перезапустите: `docker exec backend-laravel-1 supervisorctl restart reverb`

### Проблема: Порт 6001 недоступен

**Решение:**
1. Проверьте проброс порта в `docker-compose.dev.yml`
2. Проверьте, не занят ли порт: `netstat -tuln | grep 6001`
3. Перезапустите контейнер: `docker-compose restart laravel`

### Проблема: Ошибка аутентификации

**Решение:**
1. Проверьте, что пользователь авторизован (есть сессия)
2. Проверьте маршрут `/broadcasting/auth` в `routes/web.php`
3. Проверьте CSRF токен

### Проблема: Подключение устанавливается, но сразу разрывается

**Решение:**
1. Проверьте логи Reverb на ошибки
2. Проверьте таймауты в конфигурации
3. Увеличьте `activity_timeout` в `config/reverb.php`

## Включение детального логирования

Для отладки включите детальное логирование в `bootstrap.js`:
- Уже включено: `enabledLogging: true` в конфигурации Echo
- Проверьте консоль браузера на сообщения `[WebSocket]`

## Проверка после исправлений

После применения исправлений проверьте:

1. ✅ Reverb запущен и слушает порт 6001
2. ✅ Переменные окружения настроены правильно
3. ✅ В консоли браузера нет ошибок подключения
4. ✅ Статус WebSocket показывает "Подключено" через несколько секунд после загрузки страницы

---

_Обновлено: 2024-11-24_

