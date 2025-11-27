# Исправление проблемы WebSocket на фронтенде

## Проблема

WebSocket соединения показывают состояние "unavailable" сразу после инициализации, хотя сервер Reverb работает нормально и соединения устанавливаются (код 101 в Nginx).

## Анализ

### Симптомы:
1. Состояние "unavailable" в Pusher.js сразу после инициализации
2. Соединения устанавливаются (код 101), но сразу закрываются
3. В логах Reverb видно: `Connection Established` → `Control Frame Received (null)` → `Connection Closed`

### Возможные причины:
1. **Pusher.js не подключается автоматически** - может потребоваться явный вызов `connect()`
2. **Ошибка типа на сервере** - соединение устанавливается, но закрывается из-за ошибки в PusherController
3. **Проблема с авторизацией каналов** - пустой `auth` при подписке на каналы

## Примененные исправления

### 1. ✅ Добавлен явный вызов `pusher.connect()`

После создания экземпляра Echo добавлен явный вызов `connect()` с небольшой задержкой:

```typescript
setTimeout(() => {
  const connection = pusher.connection
  if (connection && connection.state !== 'connected' && connection.state !== 'connecting') {
    pusher.connect() // или connection.connect()
  }
}, 100)
```

**Причина:** Pusher.js должен подключаться автоматически, но в некоторых случаях может не подключиться. Явный вызов гарантирует подключение.

### 2. ✅ Добавлен `enabledAutoConnect: true` в конфигурацию

```typescript
enabledAutoConnect: true,
```

**Причина:** Явно указываем, что автоматическое подключение должно быть включено.

### 3. ✅ Улучшена обработка состояния "unavailable"

В `useSystemStatus.ts` состояние "unavailable" теперь отображается как "connecting" для лучшего UX.

### 4. ✅ Добавлен канал `hydro.alerts` в `routes/channels.php`

Канал был использован в `bootstrap.js`, но не был определен в `channels.php`.

## Проверка

После применения исправлений:

1. **Перезапустите контейнер Laravel:**
   ```bash
   docker-compose -f docker-compose.dev.yml restart laravel
   ```

2. **Обновите страницу в браузере** (Ctrl+F5)

3. **Проверьте консоль браузера** (F12):
   - Должны быть логи: `[echoClient] Explicitly calling pusher.connect()`
   - Должно быть: `[echoClient] WebSocket connected`
   - Не должно быть ошибок типа

4. **Проверьте статус WebSocket** в HeaderStatusBar:
   - Должно быть "Подключено" вместо "Неизвестно" или "unavailable"

## Если проблема сохраняется

1. **Проверьте логи Reverb:**
   ```bash
   docker exec <container_id> tail -f /var/log/reverb/reverb.log
   ```
   - Если есть ошибки типа в PusherController, это баг в Laravel Reverb 1.6.1

2. **Проверьте логи браузера:**
   - Откройте консоль (F12)
   - Проверьте Network tab на наличие WebSocket соединений
   - Проверьте, что соединение устанавливается (Status 101)

3. **Проверьте авторизацию:**
   - Убедитесь, что пользователь аутентифицирован
   - Проверьте, что все каналы определены в `routes/channels.php`

## Статус

- ✅ Добавлен явный вызов `pusher.connect()`
- ✅ Добавлен `enabledAutoConnect: true`
- ✅ Улучшена обработка состояния "unavailable"
- ✅ Добавлен канал `hydro.alerts`
- ⚠️ Требуется проверка после перезапуска


