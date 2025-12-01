# Исправление проблемы рассинхронизации статуса зоны

## Проблема

Ошибка 422 "Zone is not paused" возникала при попытке возобновить зону, которая уже была запущена. Это происходило из-за рассинхронизации между UI и сервером:
- UI показывал зону как приостановленную (PAUSED)
- Сервер имел зону в статусе RUNNING
- При клике на "Возобновить" отправлялся запрос `/api/zones/23/resume`
- Сервер возвращал 422, так как зона уже не была приостановлена

## Причина

1. **Zone computed не использовал store**: `zone` computed брал данные только из `page.props.zone`, не проверяя store, где может быть более актуальное состояние
2. **Нет синхронизации после ошибки**: После ошибки 422 не происходила синхронизация статуса с сервером
3. **Store не инициализировался из props**: При монтировании компонента зона не добавлялась в store

## Решение

### 1. Использование store как источника правды для zone

**Файл**: `backend/laravel/resources/js/Pages/Zones/Show.vue`

**Изменение**:
- `zone` computed теперь сначала проверяет store, потом props
- Это обеспечивает использование актуального состояния зоны

**Код**:
```typescript
const zone = computed(() => {
  const zoneIdValue = zoneId.value
  
  // Сначала проверяем store - там может быть более актуальное состояние
  if (zoneIdValue) {
    const storeZone = zonesStore.zoneById(zoneIdValue)
    if (storeZone) {
      return storeZone
    }
  }
  
  // Если в store нет, используем props
  const rawZoneData = (page.props.zone || {}) as any
  // ...
})
```

### 2. Синхронизация статуса после ошибки 422

**Изменение**:
- В обработчике `onError` добавлена проверка на ошибку 422
- При ошибке 422 зона синхронизируется с сервером через `fetchZone`
- Это предотвращает повторные ошибки при следующих попытках

**Код**:
```typescript
onError: async (error) => {
  const is422Error = error && typeof error === 'object' && 'response' in error && 
                   (error as any).response?.status === 422
  
  if (is422Error) {
    // Синхронизируем статус зоны с сервером после ошибки валидации
    const { fetchZone } = useZones(showToast)
    const serverZone = await fetchZone(zoneId.value, true)
    if (serverZone?.id) {
      zonesStore.upsert(serverZone, false)
    }
  }
}
```

### 3. Инициализация store из props при монтировании

**Изменение**:
- В `onMounted` зона инициализируется в store из props
- Это обеспечивает синхронизацию с самого начала

**Код**:
```typescript
onMounted(async () => {
  // Инициализируем зону в store из props для синхронизации
  if (zoneId.value && zone.value?.id) {
    zonesStore.upsert(zone.value, true) // silent: true, так как это начальная инициализация
  }
  // ...
})
```

### 4. Использование актуального статуса в onToggle

**Изменение**:
- `onToggle` теперь использует `zone.value`, который берет данные из store
- Это гарантирует использование актуального статуса

## Результат

После исправлений:
- ✅ Zone computed использует store как источник правды
- ✅ После ошибки 422 статус синхронизируется с сервером
- ✅ Store инициализируется из props при монтировании
- ✅ Предотвращены повторные ошибки 422

---

*Исправление выполнено: $(date)*

