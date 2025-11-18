# Диагностика проблем с WebSocket (Reverb)

## Быстрая проверка

```bash
# Запустите скрипт проверки
./check-websocket.sh

# Или вручную проверьте статус Reverb
docker exec backend-laravel-1 ps aux | grep reverb
docker exec backend-laravel-1 tail -n 50 /tmp/reverb.log
```

## Основные проблемы и решения

### 1. WebSocket показывает "Неизвестно" или "Отключено"

**Причины:**
- Reverb не запущен
- Неправильные переменные окружения
- Порт заблокирован
- Неправильная конфигурация

**Решение:**

1. Проверьте, запущен ли Reverb:
```bash
docker exec backend-laravel-1 supervisorctl status reverb
```

2. Проверьте переменные окружения:
```bash
docker exec backend-laravel-1 env | grep REVERB
docker exec backend-laravel-1 env | grep VITE
```

3. Проверьте логи:
```bash
docker exec backend-laravel-1 tail -f /tmp/reverb.log
```

4. Перезапустите Reverb:
```bash
docker exec backend-laravel-1 supervisorctl restart reverb
```

### 2. Переменные окружения не передаются на фронтенд

**Проблема:** Vite не видит переменные `VITE_*` (appKey = false)

**Решение:**

1. **Перезапустите контейнер Laravel** (чтобы docker-entrypoint.sh обновил .env файл):
```bash
docker-compose -f backend/docker-compose.dev.yml restart laravel
```

2. Проверьте, что переменные добавлены в `.env` файл внутри контейнера:
```bash
docker exec backend-laravel-1 grep VITE /app/.env
```

Должны быть строки:
```
VITE_ENABLE_WS=true
VITE_REVERB_APP_KEY=local
VITE_REVERB_HOST=localhost
VITE_REVERB_PORT=6001
```

3. **Перезапустите Vite** (если он запущен через supervisor):
```bash
docker exec backend-laravel-1 supervisorctl restart vite
```

Или пересоберите фронтенд:
```bash
docker exec backend-laravel-1 npm run build
# или для dev
docker exec backend-laravel-1 npm run dev
```

4. Проверьте в браузере (консоль):
```javascript
console.log('VITE_REVERB_APP_KEY:', import.meta.env.VITE_REVERB_APP_KEY)
console.log('VITE_ENABLE_WS:', import.meta.env.VITE_ENABLE_WS)
```

Если переменные все еще не видны:
- Убедитесь, что переменные добавлены в `docker-compose.dev.yml`
- Проверьте логи Vite: `docker exec backend-laravel-1 tail -f /tmp/vite.log`
- Очистите кеш Vite: `docker exec backend-laravel-1 rm -rf /app/node_modules/.vite`

### 3. Порт 6001 недоступен

**Проверка:**
```bash
# Проверьте, что порт открыт в Docker
docker ps | grep 6001

# Проверьте, что порт прослушивается внутри контейнера
docker exec backend-laravel-1 netstat -tuln | grep 6001

# Проверьте подключение с хоста
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:6001
```

**Решение:**
- Убедитесь, что в `docker-compose.yml` есть маппинг порта: `"6001:6001"`
- Проверьте firewall на хосте
- Убедитесь, что другой сервис не использует порт 6001

### 4. Reverb не запускается автоматически

**Проверка:**
```bash
docker exec backend-laravel-1 env | grep REVERB_AUTO_START
```

**Решение:**
- Убедитесь, что `REVERB_AUTO_START=true` в docker-compose
- Проверьте конфигурацию supervisor: `/opt/docker/etc/supervisor.d/reverb.conf`
- Запустите вручную:
```bash
docker exec backend-laravel-1 php artisan reverb:start --host=0.0.0.0 --port=6001
```

### 5. Неправильный ключ приложения

**Проблема:** Ошибка авторизации при подключении

**Решение:**
- Убедитесь, что `REVERB_APP_KEY` в бэкенде совпадает с `VITE_REVERB_APP_KEY` на фронтенде
- Проверьте в консоли браузера ошибки подключения
- Убедитесь, что используется правильный `REVERB_APP_SECRET` на бэкенде

### 6. CORS ошибки

**Проблема:** Браузер блокирует WebSocket подключение

**Решение:**
- Проверьте `allowed_origins` в `config/reverb.php`
- Убедитесь, что фронтенд и бэкенд на одном домене или правильно настроен CORS

## Проверка конфигурации

### Backend (Laravel)

1. Проверьте конфигурацию Reverb:
```bash
docker exec backend-laravel-1 php artisan config:show reverb
```

2. Проверьте broadcasting driver:
```bash
docker exec backend-laravel-1 php artisan config:show broadcasting
```

Должно быть: `BROADCAST_DRIVER=reverb`

### Frontend (Vue)

1. Откройте консоль браузера и проверьте:
```javascript
console.log('Echo:', window.Echo)
console.log('Pusher:', window.Pusher)
console.log('WS Config:', {
  host: import.meta.env.VITE_REVERB_HOST,
  port: import.meta.env.VITE_REVERB_PORT,
  key: import.meta.env.VITE_REVERB_APP_KEY
})
```

2. Проверьте подключение:
```javascript
if (window.Echo && window.Echo.connector && window.Echo.connector.pusher) {
  const pusher = window.Echo.connector.pusher
  console.log('Connection state:', pusher.connection?.state)
  console.log('Socket ID:', pusher.connection?.socket_id)
}
```

## Логи для диагностики

### Reverb логи
```bash
docker exec backend-laravel-1 tail -f /tmp/reverb.log
```

### Supervisor логи
```bash
docker exec backend-laravel-1 tail -f /var/log/supervisor/reverb*.log
```

### Laravel логи
```bash
docker exec backend-laravel-1 tail -f storage/logs/laravel.log
```

### Браузер консоль
Откройте DevTools (F12) → Console и проверьте ошибки WebSocket

## Типичные ошибки

### "Connection refused"
- Reverb не запущен
- Неправильный порт
- Firewall блокирует подключение

### "Invalid app key"
- Неправильный `REVERB_APP_KEY`
- Ключ не совпадает между бэкендом и фронтендом

### "Connection timeout"
- Reverb не отвечает
- Проблемы с сетью
- Неправильный хост

### "CORS error"
- Неправильно настроены `allowed_origins`
- Проблемы с заголовками CORS

## Перезапуск всего стека

Если ничего не помогает:

```bash
# Остановите контейнеры
docker-compose -f docker-compose.dev.yml down

# Очистите кеш Laravel
docker-compose -f docker-compose.dev.yml run --rm laravel php artisan config:clear
docker-compose -f docker-compose.dev.yml run --rm laravel php artisan cache:clear

# Запустите заново
docker-compose -f docker-compose.dev.yml up -d

# Проверьте статус
./check-websocket.sh
```

## Контакты

Если проблема не решена, соберите следующую информацию:
1. Вывод `./check-websocket.sh`
2. Последние 50 строк `/tmp/reverb.log`
3. Ошибки из консоли браузера
4. Конфигурация из `docker-compose.yml`

