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

Создан единый модуль `ws/subscriptions.ts`, который:
- Использует единую инфраструктуру `onWsStateChange` из `echoClient.ts` для resubscribe
- Предоставляет простой API для подписок на зоны и алерты
- Гарантирует правильную очистку при unmount компонентов
- Интегрируется с существующей инфраструктурой `useWebSocket.ts` для команд

### Структура

```
ws/subscriptions.ts
├── subscribeZone(zoneId, handler) → unsubscribe function
└── subscribeAlerts(handler) → unsubscribe function
```

### Ключевые принципы

1. **Единый путь resubscribe**: Все подписки используют `onWsStateChange` из `echoClient.ts`
2. **Автоматическая очистка**: Функции unsubscribe правильно очищают каналы и слушатели
3. **Минимальный bootstrap.js**: Содержит только инициализацию Echo и обработку reconciliation

## Последствия

### Положительные

- ✅ Единый механизм resubscribe после reconnect
- ✅ Нет дублирующих событий (одна нотификация не приходит дважды)
- ✅ Нет утечек (подписки снимаются при unmount)
- ✅ Упрощенная поддержка и отладка
- ✅ Минимальный bootstrap.js (только init + reconciliation)

### Ограничения

- Подписки на зоны и алерты используют прямой доступ к Echo (не через useWebSocket)
- Это допустимо, так как эти каналы не требуют сложной логики реестров/очередей

## Миграция

Компоненты, использующие старый API:
```typescript
// Старый способ (bootstrap.js)
import { subscribeAlerts } from '@/bootstrap'

// Новый способ
import { subscribeAlerts } from '@/ws/subscriptions'
```

API остался совместимым, изменился только путь импорта.

## Связанные изменения

- `bootstrap.js`: Удалены функции `subscribeZone` и `subscribeAlerts`
- `ws/subscriptions.ts`: Новый модуль для подписок
- `Pages/Alerts/Index.vue`: Обновлен импорт

