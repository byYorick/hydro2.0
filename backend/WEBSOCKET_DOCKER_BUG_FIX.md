# Исправление бага WebSocket в Docker конфигурации

## Найденная проблема

### Несоответствие в конфигурации REVERB_HOST

**Проблема:** В `docker-compose.dev.yml` было установлено `REVERB_HOST=0.0.0.0`, что неправильно для клиентских подключений.

**Почему это проблема:**
1. `0.0.0.0` - это специальный адрес для **прослушивания сервера** на всех интерфейсах
2. `0.0.0.0` **не может** использоваться для **клиентских подключений**
3. Клиент должен подключаться к конкретному адресу: `localhost`, `127.0.0.1` или доменному имени

**Где использовалось неправильно:**
- `config/reverb.php` → `'hostname' => env('REVERB_HOST', '0.0.0.0')` - для клиентских URL
- `config/reverb.php` → `'options' => ['host' => env('REVERB_HOST', '127.0.0.1')]` - для клиентских подключений

## Применённые исправления

### 1. Разделение конфигурации сервера и клиента

**Файл:** `backend/docker-compose.dev.yml`

```yaml
# Сервер слушает на всех интерфейсах (правильно)
- REVERB_SERVER_HOST=0.0.0.0
- REVERB_SERVER_PORT=6001

# Клиент подключается к localhost через nginx прокси (правильно)
- REVERB_HOST=localhost
- REVERB_CLIENT_HOST=localhost
- REVERB_PORT=6001
```

### 2. Исправление config/reverb.php

**Секция `servers`:**
```php
'reverb' => [
    // Сервер слушает на 0.0.0.0 (все интерфейсы)
    'host' => env('REVERB_SERVER_HOST', env('REVERB_HOST', '0.0.0.0')),
    
    // Клиент использует localhost для подключения
    'hostname' => env('REVERB_CLIENT_HOST', env('REVERB_HOST', 'localhost')),
],
```

**Секция `apps`:**
```php
'options' => [
    // Клиент подключается к localhost (не 0.0.0.0)
    'host' => env('REVERB_CLIENT_HOST', env('REVERB_HOST', 'localhost')),
    'port' => env('REVERB_PORT', 6001),
    // ...
],
```

## Архитектура подключения

### Development режим (через nginx прокси)

```
Браузер → ws://localhost:8080/app/local
         ↓
      Nginx (порт 8080)
         ↓
      Проксирует на /app/ → http://127.0.0.1:6001
         ↓
      Reverb (слушает на 0.0.0.0:6001)
```

**Важно:**
- Reverb **слушает** на `0.0.0.0:6001` (все интерфейсы)
- Клиент **подключается** к `localhost:8080` (через nginx)
- Nginx **проксирует** на `127.0.0.1:6001` (внутри контейнера)

### Production режим

```
Браузер → ws://example.com/app/local
         ↓
      Load Balancer / Nginx
         ↓
      Проксирует на /app/ → http://laravel:6001
         ↓
      Reverb (слушает на 0.0.0.0:6001)
```

## Переменные окружения

### Для сервера (прослушивание)
- `REVERB_SERVER_HOST=0.0.0.0` - слушать на всех интерфейсах
- `REVERB_SERVER_PORT=6001` - порт для прослушивания
- `REVERB_SERVER_PATH=` - путь (обычно пустой)

### Для клиента (подключение)
- `REVERB_HOST=localhost` - адрес для подключения (dev)
- `REVERB_CLIENT_HOST=localhost` - явный адрес для клиента (dev)
- `REVERB_PORT=6001` - порт (но в dev используется nginx прокси на 8080)
- `REVERB_SCHEME=http` - схема (ws://)

## Проверка исправления

### 1. Проверить конфигурацию Reverb

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
\$config = config('reverb');
echo 'Server host: ' . \$config['servers']['reverb']['host'] . PHP_EOL;
echo 'Server hostname: ' . \$config['servers']['reverb']['hostname'] . PHP_EOL;
echo 'Client host: ' . \$config['apps']['apps'][0]['options']['host'] . PHP_EOL;
"
```

### 2. Проверить логи Reverb

```bash
docker exec backend-laravel-1 tail -f /var/log/reverb/reverb.log
```

### 3. Проверить подключение в браузере

1. Откройте консоль разработчика (F12)
2. Перейдите на вкладку Network
3. Отфильтруйте по WS (WebSocket)
4. Проверьте, что соединение устанавливается к `ws://localhost:8080/app/local`

## Статус

- ✅ Исправлено несоответствие REVERB_HOST
- ✅ Разделены конфигурации сервера и клиента
- ✅ Добавлена переменная REVERB_CLIENT_HOST для явного указания адреса клиента
- ✅ Обновлена конфигурация config/reverb.php

## Дополнительные замечания

1. **В dev режиме** клиент подключается через nginx прокси на порту 8080, а не напрямую к 6001
2. **В production** может потребоваться другой адрес для REVERB_CLIENT_HOST (доменное имя)
3. **Порт 6001** пробрасывается в docker-compose для прямого доступа (если нужно), но в dev используется nginx прокси

