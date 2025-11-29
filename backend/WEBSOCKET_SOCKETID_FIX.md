# Исправление проблемы с socketId: undefined

## Проблема

WebSocket соединение устанавливается, но `socketId` остается `undefined`. В логах видно:
- Состояние "connecting" устанавливается
- Но `socketId` не присваивается
- Соединение может переходить в "unavailable"

## Причина

Из логов Reverb видно, что соединение устанавливается, но сразу закрывается:
```
Connection Established
Control Frame Received null
Connection Closed
```

Это означает, что:
1. Соединение устанавливается на уровне WebSocket
2. Но Reverb не может его обработать (возможно, проблема с авторизацией или типами)
3. Соединение закрывается до того, как `socketId` присваивается

## Применённые исправления

### 1. Улучшена обработка получения socketId

**Файл:** `resources/js/utils/echoClient.ts`

- Добавлена проверка, что `socketId` действительно получен после события "connected"
- Добавлено ожидание `socketId` с задержкой (иногда присваивается с небольшой задержкой)
- Улучшена обработка состояния "connecting" с проверкой `socketId`

**Код:**
```typescript
{
  event: 'connected',
  handler: () => {
    // Проверяем, что socketId действительно получен
    const socketId = connection?.socket_id
    if (!socketId) {
      logger.warn('[echoClient] Connected but socketId is undefined, waiting for socket_id', {
        connectionState: connection?.state,
      })
      // Ждем немного, возможно socketId появится
      setTimeout(() => {
        const delayedSocketId = connection?.socket_id
        if (delayedSocketId) {
          logger.info('[echoClient] socketId received after delay', {
            socketId: delayedSocketId,
          })
        } else {
          logger.error('[echoClient] socketId still undefined after delay, connection may be invalid', {
            connectionState: connection?.state,
          })
        }
      }, 500)
    }
    // ...
  },
}
```

### 2. Улучшена функция getConnectionState()

**Файл:** `resources/js/utils/echoClient.ts`

- Добавлена более надежная обработка получения `socketId`
- Добавлена обработка ошибок при получении `socketId`
- Добавлено логирование для диагностики

**Код:**
```typescript
export function getConnectionState(): {
  // ...
  socketId?: string | null
} {
  let socketId: string | null = null
  
  try {
    if (echoInstance?.connector?.pusher?.connection) {
      socketId = echoInstance.connector.pusher.connection.socket_id || null
      
      // Если socketId undefined, но соединение в состоянии connected, ждем немного
      if (!socketId && echoInstance.connector.pusher.connection.state === 'connected') {
        logger.debug('[echoClient] socketId is null but connection is connected', {
          state: echoInstance.connector.pusher.connection.state,
        })
      }
    }
  } catch (error) {
    logger.warn('[echoClient] Error getting socketId', {
      error: error instanceof Error ? error.message : String(error),
    })
  }

  return {
    // ...
    socketId,
  }
}
```

### 3. Исправлена обработка socketId в useSystemStatus

**Файл:** `resources/js/composables/useSystemStatus.ts`

- Добавлена безопасная проверка на null/undefined
- Используется optional chaining для предотвращения ошибок

**Код:**
```typescript
socketId: echo?.connector?.pusher?.connection?.socket_id || null,
```

## Известные ограничения

1. **Проблема с Reverb**: Соединение устанавливается, но сразу закрывается с "Control Frame Received null"
   - Это может быть связано с проблемой типов в PusherController (GitHub issue #212)
   - Или с проблемой авторизации каналов

2. **socketId может быть undefined**:
   - Если соединение не прошло полный цикл подключения
   - Если Reverb закрывает соединение до присвоения socketId
   - Это нормально - соединение просто не установлено полностью

## Рекомендации

1. **Мониторинг логов Reverb**:
   ```bash
   docker exec backend-laravel-1 tail -f /var/log/reverb/reverb.log
   ```

2. **Проверка авторизации**:
   - Убедитесь, что пользователь аутентифицирован
   - Проверьте логи Laravel на ошибки авторизации каналов

3. **Проверка в браузере**:
   - Откройте консоль разработчика (F12)
   - Проверьте Network tab на наличие WebSocket соединений
   - Проверьте, что соединение устанавливается (Status 101)

## Статус

- ✅ Улучшена обработка получения socketId
- ✅ Добавлена проверка socketId после подключения
- ✅ Улучшена обработка ошибок при получении socketId
- ⚠️ Проблема с Reverb (Connection Closed) требует дополнительной диагностики

