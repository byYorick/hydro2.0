# Исправление проблемы подключения WebSocket (Reverb)

## Проблема

Фронтенд пытается подключиться к `ws://localhost:6001/app/local?...` и получает ошибку `WebSocketError` (Reverb/Pusher рукопожатие не прошло).

## Основные причины

1. **Сервер Reverb не запущен** или слушает другой порт/host
2. **Неверные env переменные** для фронтенда (не совпадают с сервером)
3. **Неправильный host/port** в конфигурации
4. **Проблемы с allowed_origins** (CORS)
5. **Несовпадение app key** между сервером и клиентом

## Быстрая диагностика

### 1. Запустите скрипт диагностики

```bash
cd backend
./check-websocket.sh
```

Скрипт проверит:
- Статус контейнера Laravel
- Запущен ли процесс Reverb
- Прослушивается ли порт 6001
- Совпадение переменных окружения
- Логи Reverb

### 2. Проверка вручную

#### Проверка процесса Reverb

```bash
# В контейнере
docker exec <laravel-container> ps aux | grep reverb

# Или через supervisor
docker exec <laravel-container> supervisorctl status reverb
```

#### Проверка порта

```bash
docker exec <laravel-container> netstat -tuln | grep 6001
# или
docker exec <laravel-container> ss -tuln | grep 6001
```

#### Просмотр логов Reverb

```bash
docker exec <laravel-container> tail -f /tmp/reverb.log
```

## Исправление проблем

### Проблема 1: Reverb не запущен

**Решение:**

```bash
# Запустить через supervisor
docker exec <laravel-container> supervisorctl start reverb

# Или запустить вручную с debug
docker exec -it <laravel-container> php artisan reverb:start --debug --host=0.0.0.0 --port=6001
```

**Проверка в docker-compose.dev.yml:**

Убедитесь, что `REVERB_AUTO_START=true` установлен в переменных окружения контейнера.

### Проблема 2: Несовпадение переменных окружения

**Требования к переменным:**

В `docker-compose.dev.yml` должны быть согласованы:

```yaml
environment:
  # Сервер Reverb
  - REVERB_APP_ID=app
  - REVERB_APP_KEY=local          # Должен совпадать с VITE_REVERB_APP_KEY
  - REVERB_APP_SECRET=secret
  - REVERB_HOST=0.0.0.0           # Сервер слушает на всех интерфейсах
  - REVERB_PORT=6001              # Должен совпадать с VITE_REVERB_PORT
  - REVERB_SCHEME=http
  - BROADCAST_DRIVER=reverb       # КРИТИЧНО!
  
  # Клиент (Vite)
  - VITE_REVERB_APP_KEY=local     # Должен совпадать с REVERB_APP_KEY
  - VITE_REVERB_HOST=localhost    # Для браузера на хосте
  - VITE_REVERB_PORT=6001         # Должен совпадать с REVERB_PORT
  - VITE_REVERB_SCHEME=http
  - VITE_ENABLE_WS=true
```

**Проверка совпадения:**

```bash
# В контейнере
docker exec <laravel-container> env | grep -E "REVERB_|BROADCAST_DRIVER" | sort
```

### Проблема 3: Неправильный host для клиента

**Если фронтенд работает в браузере на хосте:**

- `VITE_REVERB_HOST=localhost` - правильно
- `REVERB_HOST=0.0.0.0` - правильно (сервер слушает на всех интерфейсах)

**Если фронтенд работает внутри контейнера:**

- `VITE_REVERB_HOST=laravel` (имя контейнера) или `127.0.0.1`
- `REVERB_HOST=0.0.0.0` - правильно

**Если используется прокси (nginx):**

- `VITE_REVERB_HOST` должен указывать на адрес, доступный из браузера
- Прокси должен быть настроен на upgrade WebSocket соединений

### Проблема 4: Проблемы с allowed_origins

Reverb проверяет Origin заголовок при подключении. Если origin не в списке разрешенных, соединение отклоняется.

**Проверка текущих allowed_origins:**

```bash
docker exec <laravel-container> php artisan config:show reverb.apps.0.allowed_origins
```

**Исправление:**

В `config/reverb.php` уже добавлены основные origins. Если нужно добавить свой:

1. Через переменную окружения:
```bash
REVERB_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://your-domain.com
```

2. Или напрямую в `config/reverb.php` (не рекомендуется для production)

### Проблема 5: BROADCAST_DRIVER не установлен

**КРИТИЧНО:** `BROADCAST_DRIVER` должен быть установлен в `reverb`.

**Проверка:**

```bash
docker exec <laravel-container> env | grep BROADCAST_DRIVER
```

**Исправление:**

В `docker-compose.dev.yml`:
```yaml
environment:
  - BROADCAST_DRIVER=reverb
```

## Пошаговая инструкция по исправлению

### Шаг 1: Проверка статуса

```bash
cd backend
./check-websocket.sh
```

### Шаг 2: Если Reverb не запущен

```bash
# Определить контейнер
LARAVEL_CONTAINER=$(docker ps | grep laravel | awk '{print $1}' | head -n1)

# Запустить Reverb
docker exec $LARAVEL_CONTAINER supervisorctl start reverb

# Проверить статус
docker exec $LARAVEL_CONTAINER supervisorctl status reverb
```

### Шаг 3: Проверка переменных окружения

```bash
# Проверить все REVERB_* переменные
docker exec $LARAVEL_CONTAINER env | grep REVERB_ | sort

# Проверить совпадение app key
REVERB_KEY=$(docker exec $LARAVEL_CONTAINER env | grep "^REVERB_APP_KEY=" | cut -d= -f2)
VITE_KEY=$(docker exec $LARAVEL_CONTAINER env | grep "^VITE_REVERB_APP_KEY=" | cut -d= -f2)
echo "REVERB_APP_KEY=$REVERB_KEY"
echo "VITE_REVERB_APP_KEY=$VITE_KEY"
if [ "$REVERB_KEY" = "$VITE_KEY" ]; then
    echo "✓ Keys совпадают"
else
    echo "✗ Keys НЕ совпадают!"
fi
```

### Шаг 4: Проверка порта

```bash
# Проверить, что порт 6001 прослушивается
docker exec $LARAVEL_CONTAINER netstat -tuln | grep 6001
# или
docker exec $LARAVEL_CONTAINER ss -tuln | grep 6001
```

### Шаг 5: Просмотр логов

```bash
# В реальном времени
docker exec $LARAVEL_CONTAINER tail -f /tmp/reverb.log

# Последние 50 строк
docker exec $LARAVEL_CONTAINER tail -n 50 /tmp/reverb.log
```

### Шаг 6: Перезапуск Reverb

```bash
# Перезапустить через supervisor
docker exec $LARAVEL_CONTAINER supervisorctl restart reverb

# Или перезапустить весь контейнер
docker-compose -f docker-compose.dev.yml restart laravel
```

### Шаг 7: Перезапуск Vite (если используется dev режим)

```bash
# Перезапустить Vite через supervisor
docker exec $LARAVEL_CONTAINER supervisorctl restart vite

# Или перезапустить весь контейнер
docker-compose -f docker-compose.dev.yml restart laravel
```

## Тестирование подключения

### Из браузера (консоль разработчика)

```javascript
// Проверить, что Echo инициализирован
console.log(window.Echo);

// Проверить состояние соединения
const pusher = window.Echo?.connector?.pusher;
console.log('Connection state:', pusher?.connection?.state);
console.log('Socket ID:', pusher?.connection?.socket_id);
```

### С помощью websocat (если установлен)

```bash
websocat ws://localhost:6001/app/local
```

### С помощью curl

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test" \
  http://localhost:6001/app/local
```

## Типичные ошибки и решения

### Ошибка: "WebSocketError: Reverb/Pusher handshake failed"

**Причины:**
1. Reverb не запущен
2. Неправильный app key
3. Проблемы с allowed_origins
4. Неправильный host/port

**Решение:** Следуйте шагам выше.

### Ошибка: "Connection refused"

**Причины:**
1. Reverb не запущен
2. Порт 6001 не проброшен в docker-compose
3. Firewall блокирует порт

**Решение:**
```bash
# Проверить проброс порта в docker-compose.dev.yml
# Должно быть:
ports:
  - "6001:6001"

# Проверить, что порт прослушивается
docker exec <container> netstat -tuln | grep 6001
```

### Ошибка: "Origin not allowed"

**Причина:** Origin браузера не в списке allowed_origins.

**Решение:**
1. Проверить текущий origin в консоли браузера: `window.location.origin`
2. Добавить его в `REVERB_ALLOWED_ORIGINS` или в `config/reverb.php`
3. Перезапустить Reverb

### Ошибка: "App key mismatch"

**Причина:** `REVERB_APP_KEY` и `VITE_REVERB_APP_KEY` не совпадают.

**Решение:**
```bash
# Убедиться, что в docker-compose.dev.yml они одинаковые
REVERB_APP_KEY=local
VITE_REVERB_APP_KEY=local
```

## Проверка после исправления

1. Запустите скрипт диагностики: `./check-websocket.sh`
2. Проверьте логи Reverb: `docker exec <container> tail -f /tmp/reverb.log`
3. Откройте консоль браузера и проверьте состояние Echo
4. Попробуйте подписаться на канал в приложении

## Дополнительные ресурсы

- [Laravel Reverb Documentation](https://laravel.com/docs/reverb)
- [Laravel Echo Documentation](https://laravel.com/docs/broadcasting#client-side-installation)
- Скрипт диагностики: `backend/check-websocket.sh`

