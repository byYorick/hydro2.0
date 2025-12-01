# Исправление проблемы rate limiting при синхронизации зоны

## Проблема

После ошибки 422 "Zone is not paused" код пытался сразу синхронизировать зону через `fetchZone`, что создавало дополнительный API запрос. Это приводило к:
1. Rate limiting (500 "Too Many Attempts")
2. Порочный круг: ошибка → синхронизация → rate limit → новая ошибка

## Причина

Синхронизация статуса зоны после ошибки 422 происходила немедленно:
```typescript
if (is422Error) {
  const serverZone = await fetchZone(zoneId.value, true) // Сразу делает запрос
  zonesStore.upsert(serverZone, false)
}
```

Это создавало последовательность запросов:
1. POST `/api/zones/24/resume` (ошибка 422)
2. GET `/api/zones/24` (синхронизация - может попасть под rate limit)

## Решение

### 1. Отложенная синхронизация

**Файл**: `backend/laravel/resources/js/Pages/Zones/Show.vue`

**Изменение**:
- Синхронизация теперь откладывается на 2 секунды после ошибки
- Это позволяет избежать немедленного повторного запроса

**Код**:
```typescript
if (is422Error) {
  // Откладываем синхронизацию на 2 секунды, чтобы избежать rate limiting
  setTimeout(() => {
    reloadZone(zoneId.value, ['zone']).catch(...)
  }, 2000)
}
```

### 2. Использование `reloadZone` вместо `fetchZone`

**Преимущества**:
- `reloadZone` использует `fetchZone` с fallback к Inertia reload
- При ошибке делает Inertia reload, который не попадает под API rate limiting
- Более надежный механизм восстановления

**Код**:
```typescript
// Было:
const serverZone = await fetchZone(zoneId.value, true)

// Стало:
reloadZone(zoneId.value, ['zone'])
```

### 3. Обработка ошибок синхронизации

**Изменение**:
- Ошибки синхронизации логируются, но не показываются пользователю
- Пользователь может обновить страницу вручную, если синхронизация не удалась

## Результат

После исправлений:
- ✅ Синхронизация откладывается, избегая rate limiting
- ✅ Используется `reloadZone` с fallback к Inertia reload
- ✅ Ошибки синхронизации обрабатываются gracefully
- ✅ Предотвращены повторные ошибки rate limiting

---

*Исправление выполнено: $(date)*

