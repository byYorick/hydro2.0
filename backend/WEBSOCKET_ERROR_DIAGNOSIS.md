# Диагностика проблемы WebSocket: соединение устанавливается, но сразу закрывается

## Наблюдаемое поведение

1. **Соединение устанавливается успешно:**
   - `socketId` присваивается: `49954570.952288820`
   - Состояние переходит в `connected`

2. **Сразу происходит ошибка:**
   - `[ERROR] [echoClient] WebSocket connection error` с "Unknown error"
   - Состояние переходит в `connecting`, затем в `unavailable`

3. **В логах Reverb:**
   ```
   Connection Established
   (иногда) Control Frame Received null
   Connection Closed
   ```

## Возможные причины

### 1. Проблема с авторизацией каналов

После установления соединения Pusher.js пытается авторизовать каналы, но авторизация не проходит:
- Запрос к `/broadcasting/auth` может не отправляться
- Или запрос отправляется, но возвращает ошибку
- Или авторизация проходит, но Reverb не может обработать ответ

### 2. Проблема с типами в PusherController

Известная проблема (GitHub issue #212):
- Ошибка: `PusherController::__invoke(): Argument #2 ($connection) must be of type Laravel\Reverb\Servers\Reverb\Connection, Laravel\Reverb\Servers\Reverb\Http\Connection given`
- Это может вызывать закрытие соединения

### 3. Проблема с обработкой сообщений

После установления соединения Reverb может получать сообщения, которые не может обработать:
- Control Frame Received null
- Неправильный формат сообщений
- Проблемы с декодированием

## Применённые исправления

### 1. Улучшена обработка ошибок в echoClient

**Файл:** `resources/js/utils/echoClient.ts`

Добавлено детальное логирование всех данных об ошибке:
- Полный payload ошибки
- Тип ошибки
- Код ошибки
- Stack trace (если доступен)
- Детали авторизации (если ошибка связана с авторизацией)

### 2. Улучшена обработка состояния "unavailable"

Добавлена задержка перед переподключением:
- Если соединение в состоянии "connecting", ждем перед переподключением
- Cooldown 5 секунд для предотвращения частых переподключений

## Диагностика

### Проверка логов Reverb

```bash
docker exec backend-laravel-1 tail -f /var/log/reverb/reverb.log | grep -E "Connection|Error|Frame|auth|Message"
```

### Проверка логов Laravel

```bash
docker exec backend-laravel-1 tail -f storage/logs/laravel.log | grep -i "broadcasting\|auth"
```

### Проверка логов nginx

```bash
docker exec backend-laravel-1 tail -f /var/log/nginx/websocket_access.log
```

### Проверка в браузере

1. Откройте консоль разработчика (F12)
2. Перейдите на вкладку Network
3. Отфильтруйте по WS (WebSocket)
4. Проверьте запросы к `/app/local`
5. Проверьте запросы к `/broadcasting/auth`

## Следующие шаги

1. **Проверить запросы авторизации:**
   - Убедиться, что запросы к `/broadcasting/auth` отправляются
   - Проверить, что они возвращают успешный ответ

2. **Проверить логи Reverb:**
   - Искать ошибки после "Connection Established"
   - Проверить, есть ли детали о закрытии соединения

3. **Проверить версию Reverb:**
   - Убедиться, что используется последняя версия
   - Проверить, есть ли известные проблемы в этой версии

4. **При необходимости обновить Reverb:**
   ```bash
   docker exec backend-laravel-1 composer update laravel/reverb
   ```

## Статус

- ✅ Улучшена обработка ошибок с детальным логированием
- ✅ Улучшена обработка состояния "unavailable"
- ⚠️ Требуется дополнительная диагностика для выявления причины закрытия соединения
- ⚠️ Возможно, связана с проблемой типов в PusherController

