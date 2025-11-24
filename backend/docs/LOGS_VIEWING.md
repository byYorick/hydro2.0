# Просмотр логов Laravel

## Где находятся логи

В dev окружении логи Laravel настроены на вывод в `stderr` (стандартный поток ошибок), поэтому они доступны через `docker logs`, а не в файлах.

## Способы просмотра логов

### 1. Через Docker команды

**Последние 50 строк:**
```bash
docker logs backend-laravel-1 --tail 50 2>&1
```

**Последние 100 строк:**
```bash
docker logs backend-laravel-1 --tail 100 2>&1
```

**Только ошибки:**
```bash
docker logs backend-laravel-1 2>&1 | grep -i "ERROR\|Exception\|Fatal" | tail -50
```

**Ошибки и предупреждения:**
```bash
docker logs backend-laravel-1 2>&1 | grep -i "ERROR\|WARNING\|Exception\|Fatal" | tail -50
```

**Следить за логами в реальном времени:**
```bash
docker logs backend-laravel-1 -f 2>&1
```

### 2. Через скрипт

Используйте удобный скрипт:
```bash
cd backend
./scripts/view-logs.sh
```

### 3. Логи Reverb (WebSocket)

Логи WebSocket сервера находятся в отдельном файле:
```bash
docker exec backend-laravel-1 tail -50 /tmp/reverb.log
```

## Настройка логирования в файл

Если вы хотите, чтобы логи также сохранялись в файл, измените переменную окружения в `docker-compose.dev.yml`:

```yaml
environment:
  - LOG_CHANNEL=single  # вместо stderr
```

Или используйте `stack` для логирования и в файл, и в stderr:
```yaml
environment:
  - LOG_CHANNEL=stack
  - LOG_STACK=single,stderr
```

После изменения перезапустите контейнер:
```bash
docker-compose restart laravel
```

Логи будут доступны в:
```bash
docker exec backend-laravel-1 tail -50 /app/storage/logs/laravel.log
```

## Уровни логирования

- **DEBUG** - отладочная информация
- **INFO** - информационные сообщения
- **WARNING** - предупреждения (не критичные проблемы)
- **ERROR** - ошибки (требуют внимания)
- **CRITICAL** - критические ошибки

## Фильтрация логов

**Только ошибки Python token:**
```bash
docker logs backend-laravel-1 2>&1 | grep "Python service token"
```

**Ошибки за последний час:**
```bash
docker logs backend-laravel-1 --since 1h 2>&1 | grep -i "ERROR"
```

**Ошибки с контекстом (5 строк до и после):**
```bash
docker logs backend-laravel-1 2>&1 | grep -i -A 5 -B 5 "ERROR"
```

## Очистка логов

**Очистить логи Docker:**
```bash
docker logs backend-laravel-1 --tail 0
```

**Очистить файл логов (если используется файловое логирование):**
```bash
docker exec backend-laravel-1 truncate -s 0 /app/storage/logs/laravel.log
```

---

_Обновлено: 2024-11-24_

