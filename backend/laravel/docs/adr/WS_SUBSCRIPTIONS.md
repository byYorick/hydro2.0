# ADR: Единый слой подписок WebSocket

**Статус:** Принято  
**Дата:** 2025-01-XX  
**Контекст:** P1 — WebSocket/Echo финализация

## Проблема

До рефакторинга существовали две параллельные модели подписки на WebSocket каналы:

1. **bootstrap.js** — содержал функции `subscribeZone()` и `subscribeAlerts()` с собственной логикой resubscribe через `onWsStateChange`
2. **useWebSocket.ts** — содержал инфраструктуру для подписок на команды зон и глобальные события с реестрами, очередями и автоматическим resubscribe

Это приводило к:
- Дублированию логики resubscribe
- Разным подходам к управлению lifecycle подписок
- Потенциальным утечкам памяти при навигации Inertia
- Сложности поддержки и отладки

## Решение

Канонический frontend WebSocket layer теперь состоит из двух entry point-ов:
- `useWebSocket.ts` для нормализованных доменных подписок (`commands`, `alerts`, `global events`, `zone updates`)
- `ws/managedChannelEvents.ts` для raw event listeners на приватных/публичных каналах с тем же reconnect/resubscribe lifecycle

`ws/subscriptions.ts` удалён как промежуточный legacy-layer.

### Структура

```
useWebSocket.ts
├── subscribeToZoneCommands(zoneId, handler)
├── subscribeToGlobalEvents(handler)
├── subscribeToZoneUpdates(zoneId, handler)
└── subscribeToAlerts(handler)

ws/managedChannelEvents.ts
└── subscribeManagedChannelEvents({ channelName, eventHandlers, ... }) → unsubscribe function
```

### Ключевые принципы

1. **Единый путь resubscribe**: Все подписки используют `onWsStateChange` из `echoClient.ts`
2. **Автоматическая очистка**: Функции unsubscribe правильно очищают listeners и resubscribe state
3. **Минимальный bootstrap.js**: Содержит только инициализацию Echo и обработку reconciliation
4. **Запрет на page-level Echo API**: страницы и composables не обращаются к `Echo.private(...)` напрямую

## Последствия

### Положительные

- ✅ Единый механизм resubscribe после reconnect
- ✅ Нет дублирующих событий (одна нотификация не приходит дважды)
- ✅ Нет утечек (подписки снимаются при unmount)
- ✅ Упрощенная поддержка и отладка
- ✅ Минимальный bootstrap.js (только init + reconciliation)

### Ограничения

- Raw listeners по-прежнему требуют явного описания event names в consumer code
- Но lifecycle/resubscribe для них централизован в `managedChannelEvents`

## Миграция

Компоненты, использующие raw события:
```typescript
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
```

## Связанные изменения

- `bootstrap.js`: Удалены функции `subscribeZone` и `subscribeAlerts`
- `ws/managedChannelEvents.ts`: Канонический managed-layer для raw событий
- `useWebSocket.ts`: Канонический managed-layer для нормализованных событий
