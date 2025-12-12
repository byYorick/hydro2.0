# Frontend Development Guide

## WebSocket Testing and Debugging

### Симуляция Reconnect

Для тестирования поведения WebSocket при переподключении можно использовать следующие методы:

#### 1. Отключение сети в браузере

**Chrome DevTools:**
1. Откройте DevTools (F12)
2. Перейдите на вкладку **Network**
3. Выберите **Offline** в выпадающем списке режимов сети
4. Подождите несколько секунд
5. Вернитесь в режим **Online**

**Firefox DevTools:**
1. Откройте DevTools (F12)
2. Перейдите на вкладку **Network**
3. Установите чекбокс **Disable cache** и выберите **Offline** в выпадающем списке

#### 2. Перезапуск Laravel Reverb

```bash
# Остановить Reverb
php artisan reverb:stop

# Запустить снова
php artisan reverb:start
```

Или если используете Supervisor/systemd:
```bash
sudo systemctl restart reverb
# или
sudo supervisorctl restart reverb
```

#### 3. Блокировка WebSocket порта (Linux/Mac)

```bash
# Блокировать порт (обычно 8080)
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP

# Разблокировать
sudo iptables -D INPUT -p tcp --dport 8080 -j DROP
```

#### 4. Использование DevTools Console

В консоли браузера можно принудительно отключить Echo:

```javascript
// Отключить соединение
if (window.Echo?.connector?.pusher) {
  window.Echo.connector.pusher.disconnect()
}

// Подождать и переподключить
setTimeout(() => {
  if (window.Echo?.connector?.pusher) {
    window.Echo.connector.pusher.connect()
  }
}, 5000)
```

### Проверка инвариантов подписок

В режиме разработки (DEV) автоматически включен self-check режим для проверки инвариантов подписок.

#### Просмотр статистики подписок

В консоли браузера:

```javascript
// Получить статистику всех активных подписок
window.__wsInvariants.getStats()

// Проверить инварианты вручную
window.__wsInvariants.checkInvariants()

// Очистить реестр (для тестирования)
window.__wsInvariants.clearRegistry()
```

#### Что проверяется автоматически:

1. **Дублирование подписок** - предупреждение, если одна и та же подписка регистрируется дважды
2. **Утечки памяти** - проверка корректной очистки при unmount компонентов
3. **Подозрительно большое количество подписок** - предупреждение при >10 подписок на один канал

#### Отключение инвариантов

Если нужно отключить проверку инвариантов (не рекомендуется):

```bash
# В .env
VITE_WS_INVARIANTS=false
```

### Отладка WebSocket соединения

#### Проверка состояния соединения

```javascript
// В консоли браузера
const echo = window.Echo
if (echo?.connector?.pusher) {
  const connection = echo.connector.pusher.connection
  console.log('State:', connection.state)
  console.log('Socket ID:', connection.socket_id)
}
```

#### Логирование событий WebSocket

Все события WebSocket логируются через `logger`. Для просмотра в консоли:

```javascript
// Включить debug логирование
localStorage.setItem('debug', 'ws:*')
```

### Тестирование подписок

#### Unit-тесты

Запуск unit-тестов для инвариантов:

```bash
npm run test ws/invariants
```

#### Browser тесты

Для полного E2E тестирования WebSocket используйте Dusk тесты:

```bash
php artisan dusk
```

### Известные проблемы

1. **Дублирование событий при быстром reconnect**
   - Решение: используйте reconciliation через snapshot
   - Проверка: `window.__wsInvariants.checkInvariants()`

2. **Утечки памяти при навигации Inertia**
   - Решение: убедитесь, что все подписки отписываются в `onUnmounted`
   - Проверка: `window.__wsInvariants.getStats()` до и после навигации

3. **Каналы не восстанавливаются после reconnect**
   - Решение: используйте единый механизм resubscribe через `onWsStateChange`
   - Проверка: логи в консоли должны показывать "resubscribing"

### Полезные ссылки

- [Laravel Reverb Documentation](https://reverb.laravel.com)
- [Laravel Echo Documentation](https://laravel.com/docs/broadcasting#client-side-installation)
- [Pusher Protocol](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)

