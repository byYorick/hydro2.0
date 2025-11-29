# Включение детального логирования Reverb

## Применённые настройки

### 1. Максимальный уровень детализации в команде

**Файл:** `backend/laravel/reverb-supervisor.conf`

```ini
command=php /app/artisan reverb:start --host=0.0.0.0 --port=6001 --debug -vvv
```

- `--debug` - включает режим отладки
- `-vvv` - максимальный уровень детализации (3 уровня verbose)

### 2. Увеличен размер логов

```ini
stdout_logfile_maxbytes=100MB
stdout_logfile_backups=20
```

- Увеличен максимальный размер лога до 100MB
- Увеличено количество бэкапов до 20

### 3. Переменные окружения для детального логирования

**Файл:** `backend/docker-compose.dev.yml`

```yaml
- LOG_CHANNEL=stderr
- LOG_LEVEL=debug
- APP_DEBUG=true
- REVERB_DEBUG=true
- REVERB_VERBOSE=true
```

### 4. Конфигурация Reverb

**Файл:** `backend/laravel/config/reverb.php`

Добавлена опция `verbose` в конфигурацию сервера:
```php
'options' => [
    'tls' => [],
    'debug' => env('REVERB_DEBUG', false),
    'verbose' => env('REVERB_VERBOSE', env('REVERB_DEBUG', false)),
],
```

## Просмотр логов

### Просмотр логов Reverb в реальном времени

```bash
docker exec backend-laravel-1 tail -f /var/log/reverb/reverb.log
```

### Просмотр последних 100 строк

```bash
docker exec backend-laravel-1 tail -100 /var/log/reverb/reverb.log
```

### Просмотр логов Laravel

```bash
docker exec backend-laravel-1 tail -f storage/logs/laravel.log | grep -i "broadcasting\|auth\|reverb"
```

### Просмотр всех логов с фильтрацией

```bash
docker exec backend-laravel-1 tail -f /var/log/reverb/reverb.log | grep -E "Connection|Error|Frame|auth"
```

## Что логируется

С детальным логированием (`-vvv`) Reverb будет логировать:

1. **Все соединения:**
   - Установление соединения
   - Закрытие соединения
   - Состояние соединения

2. **Все сообщения:**
   - Входящие сообщения
   - Исходящие сообщения
   - Control frames
   - Data frames

3. **Ошибки:**
   - Ошибки обработки соединений
   - Ошибки авторизации
   - Ошибки типов (PusherController)
   - Все исключения

4. **Авторизация:**
   - Запросы авторизации каналов
   - Результаты авторизации
   - Ошибки авторизации

5. **Внутренние операции:**
   - Очистка неактивных соединений
   - Ping неактивных соединений
   - Обработка сообщений

## Статус

- ✅ Максимальный уровень детализации включен (`-vvv`)
- ✅ Размер логов увеличен до 100MB
- ✅ Количество бэкапов увеличено до 20
- ✅ Все переменные окружения для детального логирования установлены
- ✅ Конфигурация Reverb обновлена

## Примечания

- Логи могут быть очень большими при активном использовании
- Рекомендуется мониторить размер логов
- В production можно уменьшить уровень детализации до `-v` или `--debug`

