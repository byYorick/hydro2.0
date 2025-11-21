# Анализ архитектуры и план улучшений

## Текущее состояние

### Frontend архитектура

#### 1. Bootstrap и инициализация (`app.js`)
✅ **Реализовано:**
- Vue 3 + Inertia.js SPA bootstrap
- Pinia store для состояния
- Глобальная регистрация виртуализаторов (`RecycleScroller`, `DynamicScroller`, `DynamicScrollerItem`)
- Verbose error/warn handlers для отладки
- Ziggy routing для Laravel routes

#### 2. Pinia Stores
⚠️ **Текущие проблемы:**
- **Простая структура**: Только `items` массив без нормализации
- **Нет состояния загрузки**: Не отслеживается `loading`, `error`, `lastFetch`
- **Нет координации**: Каждый компонент сам управляет обновлением
- **Нет инвалидации кеша**: Кеш не инвалидируется при изменениях
- **Нет lifecycle-awareness**: Не учитывается lifecycle узлов при присвоении

**Пример (zones.ts):**
```typescript
// Простой массив без нормализации
state: () => ({
  items: [] as Zone[]
})

// Нет загрузки/ошибок
// Нет инвалидации кеша
// Нет координации между экранами
```

#### 3. Создание зон и присвоение узлов
⚠️ **Текущие проблемы:**
- **Admin/Zones.vue**: Простой POST запрос без lifecycle-aware логики
- **Нет валидации lifecycle**: Frontend не проверяет, может ли узел быть присвоен к зоне
- **Нет отображения lifecycle состояний**: UI не показывает lifecycle состояние узлов
- **Нет использования NodeLifecycleService**: Frontend не использует lifecycle сервис

### Backend архитектура

#### 1. REST API и Rate Limiting
✅ **Реализовано:**
- Многоуровневое rate limiting:
  - `/auth` - 10 req/min (защита от брутфорса)
  - `/system/health` - 30 req/min (публичные эндпоинты)
  - Session auth - 60 req/min (основные API)
- Централизованные routes в `routes/api.php`
- Eager loading для предотвращения N+1

#### 2. NodeLifecycleService
✅ **Реализовано:**
- Строгие переходы состояний:
  ```
  MANUFACTURED → UNPROVISIONED → PROVISIONED_WIFI → REGISTERED_BACKEND 
  → ASSIGNED_TO_ZONE → ACTIVE/DEGRADED/MAINTENANCE/DECOMMISSIONED
  ```
- Валидация переходов в `transition()`
- Транзакционность изменений
- Логирование всех переходов
- Автоматическое обновление `status` при переходе в ACTIVE/DEGRADED/MAINTENANCE

⚠️ **Проблемы:**
- **NodeService.update** частично использует lifecycle (только при присвоении к зоне)
- **Нет API эндпоинтов** для lifecycle переходов (только внутренние методы)
- **Frontend не знает** о lifecycle переходах

#### 3. Zone Service и Recipes
✅ **Реализовано:**
- Транзакционное изменение фаз
- Валидация фаз
- Автоматический запуск аналитики при завершении рецепта
- События для уведомления Python-сервисов

### Интеграция Frontend ↔ Backend

#### 1. Телеметрия и команды
⚠️ **Проблемы:**
- **Rate limiting не учитывается**: Frontend может превысить лимиты при polling
- **Нет exponential backoff**: При ошибках повторные запросы идут без задержки
- **WebSocket resubscription** не учитывает lifecycle состояние узлов
- **Streaming endpoints** не проверяют доступность узлов по lifecycle

#### 2. Создание и присвоение
⚠️ **Проблемы:**
- **Admin/Zones.vue** не валидирует lifecycle перед присвоением узлов
- **Нет UI для lifecycle переходов**: Оператор не может управлять lifecycle узлов
- **Нет feedback**: Оператор не видит, почему узел не может быть присвоен

---

## План улучшений

### Фаза 1: Улучшение Pinia Stores

#### 1.1. Нормализация данных
```typescript
// stores/zones.ts
interface ZonesStoreState {
  // Нормализованная структура
  items: Record<number, Zone>
  ids: number[]
  
  // Состояние загрузки
  loading: boolean
  error: string | null
  lastFetch: Date | null
  
  // Инвалидация кеша
  cacheVersion: number
  cacheInvalidatedAt: Date | null
}
```

#### 1.2. Состояние загрузки
```typescript
actions: {
  async fetchZones() {
    this.loading = true
    this.error = null
    try {
      const response = await api.get('/api/zones')
      // Нормализация и обновление
      this.setZones(response.data.data)
    } catch (err) {
      this.error = handleError(err)
    } finally {
      this.loading = false
      this.lastFetch = new Date()
    }
  },
  
  invalidateCache() {
    this.cacheVersion++
    this.cacheInvalidatedAt = new Date()
  }
}
```

#### 1.3. Координация между экранами
```typescript
// Использование events или composables для синхронизации
watch(() => zoneStore.cacheVersion, (newVersion) => {
  // Обновить данные на всех экранах
  refreshAllZoneViews()
})
```

### Фаза 2: Lifecycle-aware операции

#### 2.1. API эндпоинты для lifecycle
```php
// routes/api.php
Route::post('nodes/{node}/lifecycle/transition', [NodeController::class, 'transitionLifecycle'])
  ->middleware('throttle:60,1');
  
Route::get('nodes/{node}/lifecycle/allowed-transitions', [NodeController::class, 'getAllowedTransitions'])
  ->middleware('throttle:60,1');
```

#### 2.2. Frontend composable для lifecycle
```typescript
// composables/useNodeLifecycle.ts
export function useNodeLifecycle() {
  const { api } = useApi()
  
  async function transitionNode(
    nodeId: number, 
    targetState: NodeLifecycleState, 
    reason?: string
  ) {
    const response = await api.post(`/api/nodes/${nodeId}/lifecycle/transition`, {
      target_state: targetState,
      reason
    })
    return response.data
  }
  
  async function getAllowedTransitions(nodeId: number) {
    const response = await api.get(`/api/nodes/${nodeId}/lifecycle/allowed-transitions`)
    return response.data.allowed_transitions
  }
  
  return { transitionNode, getAllowedTransitions }
}
```

#### 2.3. Валидация при присвоении узлов
```typescript
// Pages/Admin/Zones.vue
async function assignNodeToZone(nodeId: number, zoneId: number) {
  // Проверяем lifecycle состояние
  const node = devicesStore.deviceById(nodeId)
  if (!node || node.lifecycle_state !== 'REGISTERED_BACKEND') {
    showError('Узел должен быть зарегистрирован (REGISTERED_BACKEND) перед присвоением к зоне')
    return
  }
  
  // Выполняем присвоение (backend автоматически переведет в ASSIGNED_TO_ZONE)
  await api.post(`/api/nodes/${nodeId}`, { zone_id: zoneId })
  
  // Обновляем lifecycle состояние в store
  devicesStore.invalidateCache()
}
```

### Фаза 3: Rate limiting и retry логика

#### 3.1. Composable для rate-aware запросов
```typescript
// composables/useRateLimitedApi.ts
export function useRateLimitedApi() {
  const requestQueue = ref<Array<() => Promise<any>>>([])
  const isProcessing = ref(false)
  
  async function rateLimitedRequest<T>(
    requestFn: () => Promise<T>,
    options: { retries?: number; backoff?: 'exponential' | 'linear' } = {}
  ): Promise<T> {
    const { retries = 3, backoff = 'exponential' } = options
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        return await requestFn()
      } catch (err: any) {
        // Проверяем rate limit
        if (err.response?.status === 429) {
          const retryAfter = err.response.headers['retry-after'] || Math.pow(2, attempt)
          await sleep(retryAfter * 1000)
          continue
        }
        
        // Другие ошибки
        if (attempt === retries) throw err
        const delay = backoff === 'exponential' 
          ? Math.pow(2, attempt) * 1000 
          : (attempt + 1) * 1000
        await sleep(delay)
      }
    }
    
    throw new Error('Max retries exceeded')
  }
  
  return { rateLimitedRequest }
}
```

#### 3.2. WebSocket resubscription с lifecycle
```typescript
// composables/useWebSocket.ts
function resubscribeAllChannels() {
  // Фильтруем узлы по lifecycle состоянию
  const eligibleNodes = devicesStore.items.filter(node => 
    node.lifecycle_state === 'REGISTERED_BACKEND' ||
    node.lifecycle_state === 'ASSIGNED_TO_ZONE' ||
    node.lifecycle_state === 'ACTIVE' ||
    node.lifecycle_state === 'DEGRADED'
  )
  
  eligibleNodes.forEach(node => {
    subscribeToNodeCommands(node.id, handleCommand)
  })
}
```

### Фаза 4: UI для lifecycle управления

#### 4.1. Компонент для lifecycle переходов
```vue
<!-- Components/NodeLifecycleTransition.vue -->
<template>
  <div>
    <select 
      :value="currentState" 
      @change="onStateChange"
      :disabled="loading"
    >
      <option 
        v-for="state in allowedTransitions" 
        :key="state.value"
        :value="state.value"
      >
        {{ state.label }}
      </option>
    </select>
    <Button @click="transition" :disabled="loading || !selectedState">
      Перейти
    </Button>
  </div>
</template>

<script setup>
const { nodeId } = defineProps<{ nodeId: number }>()
const { transitionNode, getAllowedTransitions } = useNodeLifecycle()

const allowedTransitions = ref([])
const selectedState = ref(null)
const loading = ref(false)

onMounted(async () => {
  allowedTransitions.value = await getAllowedTransitions(nodeId)
})
</script>
```

#### 4.2. Индикаторы lifecycle состояния
```vue
<!-- Components/NodeLifecycleBadge.vue -->
<template>
  <Badge 
    :variant="getVariant(lifecycleState)"
    :title="getLabel(lifecycleState)"
  >
    {{ getLabel(lifecycleState) }}
  </Badge>
</template>
```

### Фаза 5: Кеш инвалидация и координация

#### 5.1. Система событий для координации
```typescript
// composables/useStoreEvents.ts
import { EventEmitter } from 'events'

export const storeEvents = new EventEmitter()

// В zones store
actions: {
  upsert(zone: Zone) {
    // ... обновление
    storeEvents.emit('zone:updated', zone)
  },
  
  remove(zoneId: number) {
    // ... удаление
    storeEvents.emit('zone:deleted', zoneId)
  }
}

// В компонентах
onMounted(() => {
  storeEvents.on('zone:updated', (zone) => {
    // Обновить локальное состояние
    refreshZoneView(zone)
  })
})
```

#### 5.2. Автоматическая инвалидация кеша
```typescript
// stores/zones.ts
actions: {
  async attachRecipe(zoneId: number, recipeId: number) {
    await api.post(`/api/zones/${zoneId}/attach-recipe`, { recipe_id: recipeId })
    
    // Инвалидируем кеш зон и рецептов
    this.invalidateCache()
    recipesStore.invalidateCache()
    
    // Уведомляем другие экраны
    storeEvents.emit('zone:recipe:attached', { zoneId, recipeId })
  }
}
```

---

## Приоритизация

### Критично (Следующий спринт)
1. ✅ **Rate limiting и retry логика** - предотвращение превышения лимитов
2. ✅ **Lifecycle-aware валидация** - проверка lifecycle при присвоении узлов
3. ✅ **API эндпоинты для lifecycle** - возможность управления lifecycle через API

### Важно (Следующий месяц)
4. **Нормализация stores** - улучшение производительности и координации
5. **Состояние загрузки** - лучший UX при операциях
6. **UI для lifecycle** - возможность управления lifecycle через UI

### Желательно (Будущие спринты)
7. **Координация между экранами** - автоматическая синхронизация
8. **Кеш инвалидация** - умная инвалидация кеша
9. **Оптимистичные обновления** - улучшение отзывчивости UI

---

## Метрики успеха

### Технические метрики
- ✅ **Rate limit violations**: < 1% от всех запросов
- ✅ **Lifecycle validation errors**: < 5% от присвоений
- ✅ **Cache hit rate**: > 80% для повторных запросов
- ✅ **Store synchronization**: < 100ms задержка между экранами

### UX метрики
- ✅ **Time to feedback**: < 500ms для операций
- ✅ **Error clarity**: 100% ошибок имеют понятные сообщения
- ✅ **Lifecycle visibility**: 100% узлов показывают lifecycle состояние

---

## Следующие шаги

1. **Имплементировать rate limiting и retry логику** (Фаза 3.1)
2. **Добавить API эндпоинты для lifecycle** (Фаза 2.1)
3. **Добавить lifecycle-aware валидацию** (Фаза 2.3)
4. **Добавить UI индикаторы lifecycle** (Фаза 4.2)
5. **Улучшить stores с нормализацией** (Фаза 1.1-1.2)

