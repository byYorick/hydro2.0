# Исправление проблемы "too much recursion"

## Проблема

Ошибка "too much recursion" возникала из-за бесконечного цикла между:
1. Обработчиком события `zone:updated` в `Index.vue`
2. `useBatchUpdates` → `zonesStore.upsert`
3. `zonesStore.upsert` → эмитит событие `zone:updated`
4. И снова обработчик события...

## Решение

### 1. Добавлена проверка на одинаковые данные в `upsert`

**Файл**: `backend/laravel/resources/js/stores/zones.ts`

**Изменение**:
- Добавлена проверка: если зона не изменилась (сравнение по JSON), не обновляем и не эмитим события
- Добавлен параметр `silent: boolean = false` для предотвращения эмиссии событий

**Код**:
```typescript
upsert(zone: Zone, silent: boolean = false): void {
  // Проверяем, изменилась ли зона
  if (exists) {
    const existingJson = JSON.stringify(exists)
    const newJson = JSON.stringify(zone)
    if (existingJson === newJson) {
      // Данные не изменились, не обновляем и не эмитим события
      return
    }
  }
  
  // Эмитим события только если не silent
  if (!silent) {
    zoneEvents.updated(zone)
  }
}
```

### 2. Использование `silent: true` в обработчиках событий

**Файл**: `backend/laravel/resources/js/Pages/Zones/Index.vue`

**Изменение**:
- В обработчиках событий `zone:updated` и `zone:created` используем `silent: true`
- Это предотвращает эмиссию новых событий, так как события уже были эмитнуты извне

**Код**:
```typescript
subscribeWithCleanup('zone:updated', (zone: Zone) => {
  // Используем batch updates с silent: true
  addZoneUpdate(zone)
})

// В batch updates используем silent: true
zonesStore.upsert(zone, true)
```

### 3. Прямые вызовы из API не используют `silent`

**Обоснование**:
- Если `upsert` вызывается напрямую из API (не из обработчика события), используем `silent: false`
- Это позволяет другим компонентам получить уведомление об обновлении

## Результат

После исправлений:
- ✅ Рекурсия устранена
- ✅ Обработчики событий обновляют store без создания новых событий
- ✅ Прямые обновления из API все еще эмитят события для синхронизации
- ✅ Проверка на одинаковые данные предотвращает ненужные обновления

---

*Исправление выполнено: $(date)*

