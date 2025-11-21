# Исправления ошибок WebSocket

## Исправленные проблемы

### 1. ✅ `logger.debug is not a function`
**Проблема**: При вызове `resubscribeAllChannels()` из `bootstrap.js` возникала ошибка, что `logger.debug` не является функцией.

**Решение**: Добавлены проверки на существование `logger.debug` перед вызовом во всех местах использования в `resubscribeAllChannels()`:
- Строка 284: проверка перед первым вызовом
- Строка 324: проверка при переподписке на zone commands
- Строка 341: проверка при переподписке на global events
- Строка 348: проверка при завершении переподписки

### 2. ✅ `channel.leave is not a function`
**Проблема**: При отписке от каналов возникала ошибка, что `channel.leave()` не является функцией.

**Решение**: 
- Добавлены проверки `typeof channel.leave === 'function'` перед вызовом в функциях `unsubscribe`:
  - Строка 142: для zone commands
  - Строка 221: для global events
- Обновлен интерфейс `EchoChannel`, чтобы `leave` был опциональным (`leave?: () => void`)

## Измененные файлы

- `backend/laravel/resources/js/composables/useWebSocket.ts`

## Результат

Теперь WebSocket работает корректно:
- ✅ Нет ошибок при переподписке при reconnect
- ✅ Нет ошибок при отписке от каналов
- ✅ Все проверки на существование методов добавлены

