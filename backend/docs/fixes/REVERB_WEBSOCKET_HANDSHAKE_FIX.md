# Исправление проблемы WebSocket handshake с Reverb

## Проблема

Соединение падает на рукопожатии: фронтенд пытается подключиться к `ws://localhost:6001/app/local?...`, но Reverb не отвечает или отклоняет соединение.

## Решение

### 1. Убедиться, что Reverb запущен

**Проверка:**
```bash
# Проверить, что порт 6001 прослушивается
docker exec <laravel-container> netstat -tuln | grep 6001
# или
docker exec <laravel-container> ss -tuln | grep 6001
```

**Запуск Reverb:**
```bash
# Вручную с debug
docker exec -it <laravel-container> php artisan reverb:start --host=0.0.0.0 --port=6001 --debug

# Или через supervisor (если настроен)
docker exec <laravel-container> supervisorctl start reverb
```

### 2. Синхронизация ключей и host/port

**В `docker-compose.dev.yml` должны совпадать:**

```yaml
environment:
  # Сервер Reverb
  - REVERB_APP_KEY=local          # ДОЛЖЕН СОВПАДАТЬ
  - REVERB_APP_SECRET=secret
  - REVERB_APP_ID=app
  - REVERB_HOST=0.0.0.0           # Сервер слушает на всех интерфейсах
  - REVERB_PORT=6001              # ДОЛЖЕН СОВПАДАТЬ
  - REVERB_SCHEME=http            # ДОЛЖЕН СОВПАДАТЬ
  - BROADCAST_DRIVER=reverb       # КРИТИЧНО!
  
  # Клиент (Vite)
  - VITE_REVERB_APP_KEY=local     # ДОЛЖЕН СОВПАДАТЬ с REVERB_APP_KEY
  - VITE_REVERB_HOST=localhost    # Для браузера на хосте
  - VITE_REVERB_PORT=6001         # ДОЛЖЕН СОВПАДАТЬ с REVERB_PORT
  - VITE_REVERB_SCHEME=http       # ДОЛЖЕН СОВПАДАТЬ с REVERB_SCHEME
```

**Проверка совпадения:**
```bash
docker exec <laravel-container> env | grep -E "^REVERB_|^VITE_REVERB_" | sort
```

### 3. Конфигурация allowed_origins

В `config/reverb.php` должны быть разрешены origins, с которых подключается браузер:

```php
'allowed_origins' => [
    'http://localhost:8080',    // Nginx proxy для Laravel
    'http://127.0.0.1:8080',    // Альтернативный localhost
    'http://localhost:5173',    // Vite dev server
    'http://127.0.0.1:5173',    // Vite dev server альтернативный
    'http://localhost',         // Базовый localhost
    'http://127.0.0.1',         // Альтернативный localhost
],
```

**Проверка текущего origin в браузере:**
```javascript
console.log(window.location.origin)
```

### 4. Nginx прокси для WebSocket (если используется)

Если фронтенд обращается через nginx (порт 8080), нужно добавить прокси для Reverb:

**В `nginx-vite-proxy.conf`:**
```nginx
# Прокси для Laravel Reverb WebSocket (порт 6001)
location /app/ {
    proxy_pass http://127.0.0.1:6001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_bypass $http_upgrade;
    proxy_read_timeout 86400;
    proxy_connect_timeout 7d;
    proxy_send_timeout 7d;
}
```

**ВАЖНО:** Этот блок должен быть ДО `location /` для приоритета.

### 5. Автоматический запуск Reverb через supervisor

**Конфигурация `reverb-supervisor.conf`:**
```ini
[program:reverb]
process_name=%(program_name)s
command=php /app/artisan reverb:start --host=0.0.0.0 --port=6001 --debug
directory=/app
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
user=application
numprocs=1
redirect_stderr=true
stdout_logfile=/tmp/reverb.log
stopwaitsecs=10
priority=998
```

**Проверка supervisor:**
```bash
docker exec <laravel-container> supervisorctl status reverb
```

### 6. Тестирование подключения

**С хоста:**
```bash
curl -v -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: http://localhost:8080" \
  http://localhost:6001/app/local
```

**Ожидаемый ответ:**
```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
```

### 7. Диагностика проблем

**Если Reverb не запускается:**
1. Проверить логи: `docker exec <container> tail -f /tmp/reverb.log`
2. Проверить права на файлы
3. Проверить, что порт 6001 не занят другим процессом

**Если "Invalid app key":**
- Убедиться, что `REVERB_APP_KEY` и `VITE_REVERB_APP_KEY` совпадают
- Перезапустить Vite и Reverb
- Очистить кеш браузера

**Если "Origin not allowed":**
- Проверить текущий origin: `console.log(window.location.origin)`
- Добавить его в `allowed_origins` в `config/reverb.php`
- Перезапустить Reverb

**Если соединение не устанавливается:**
- Проверить, что порт 6001 проброшен в `docker-compose.dev.yml`: `ports: - "6001:6001"`
- Проверить firewall
- Проверить, что Reverb слушает на `0.0.0.0`, а не только на `127.0.0.1`

### 8. После исправлений

1. Перезапустить Reverb:
```bash
docker exec <container> php artisan reverb:restart
# или
docker-compose -f docker-compose.dev.yml restart laravel
```

2. Перезапустить Vite (если используется):
```bash
docker exec <container> supervisorctl restart vite
```

3. Перезагрузить страницу в браузере (Ctrl+Shift+R для очистки кеша)

4. Проверить в консоли браузера:
```javascript
console.log(window.Echo?.connector?.pusher?.connection?.state)
// Должно быть: "connected"
```

## Чек-лист

- [ ] Reverb запущен и слушает порт 6001
- [ ] `REVERB_APP_KEY` и `VITE_REVERB_APP_KEY` совпадают
- [ ] `REVERB_PORT` и `VITE_REVERB_PORT` совпадают (6001)
- [ ] `REVERB_SCHEME` и `VITE_REVERB_SCHEME` совпадают (http)
- [ ] `BROADCAST_DRIVER=reverb` установлен
- [ ] Origin браузера в списке `allowed_origins`
- [ ] Порт 6001 проброшен в docker-compose
- [ ] Nginx прокси настроен (если используется)
- [ ] Reverb перезапущен после изменений
- [ ] Vite перезапущен (если используется)
- [ ] Страница перезагружена в браузере

