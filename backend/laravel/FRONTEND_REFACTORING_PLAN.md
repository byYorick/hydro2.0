# План рефакторинга фронтенда - Устранение дублирования кода

**Дата создания:** 2025-11-27  
**Дата завершения:** 2025-01-27  
**Статус:** ✅ **РЕФАКТОРИНГ ЗАВЕРШЕН**  
**Обновлено:** Согласно лучшим практикам Vue.js 3 и Inertia.js

---

## 🎯 Основные принципы рефакторинга

### Vue.js Best Practices
Согласно [официальной документации Vue.js](https://vuejs.org/guide/introduction.html), **Composition API + Single-File Components** рекомендуется для production приложений с build tools:
- `<script setup lang="ts">` вместо Options API
- TypeScript для типизации
- Composables для переиспользования логики

### Inertia.js Best Practices
Согласно лучшим практикам Inertia.js:
- ✅ Использовать `only` для partial reloads (оптимизация производительности)
- ✅ Использовать `preserveScroll` для сохранения позиции прокрутки
- ✅ Использовать `preserveState` для сохранения локального состояния компонента
- ✅ Обрабатывать `onSuccess`, `onError`, `onFinish` callbacks в формах
- ✅ Использовать `Link` компонент вместо `router.visit()` для навигации где возможно

### Использование Composition API с `<script setup>`
Согласно [Vue.js документации](https://vuejs.org/guide/introduction.html), **Composition API + Single-File Components** рекомендуется для production приложений с build tools. Все компоненты должны использовать:
- `<script setup lang="ts">` вместо Options API
- TypeScript для типизации
- Композаблы для переиспользования логики

### Приоритеты:
1. ✅ **Composition API** - использовать `<script setup>` везде
2. ✅ **TypeScript** - все компоненты должны быть типизированы
3. ✅ **Composables** - вынести повторяющуюся логику в композаблы
4. ✅ **Single-File Components** - логика, шаблон и стили в одном файле

---

## 📊 Обзор проблем

### Обнаруженные проблемы:

1. ✅ **Дублирующиеся Button компоненты** - PrimaryButton, SecondaryButton, DangerButton
2. ✅ **Прямые вызовы axios** - вместо использования useApi composable
3. ✅ **Дублирование логики loading** - создание ref(false) в каждом компоненте
4. ✅ **Дублирование обработки ошибок** - разная логика в разных местах
5. ✅ **Дублирование readBooleanEnv** - в useWebSocket и echoClient
6. ✅ **Дублирование логики модальных окон** - повторяющийся код
7. ✅ **Дублирование логики форм** - работа с Inertia формами
8. ✅ **Дублирование логики обработки API ответов** - парсинг данных

---

## 🎯 План рефакторинга

### 1. Унификация Button компонентов

**Проблема:**
- `PrimaryButton.vue`, `SecondaryButton.vue`, `DangerButton.vue` дублируют функциональность
- Уже есть универсальный `Button.vue` с вариантами (primary, secondary, outline, ghost)

**Решение:**
- Удалить дублирующие компоненты
- Заменить все использования на `Button.vue` с соответствующим `variant` prop

**Файлы для изменения:**
```
resources/js/Components/
├── PrimaryButton.vue          [УДАЛИТЬ]
├── SecondaryButton.vue        [УДАЛИТЬ]
└── DangerButton.vue           [УДАЛИТЬ]

Components/
├── ConfirmModal.vue           [ИСПРАВИТЬ] - использовать Button
├── Modal.vue                  [ИСПРАВИТЬ] - использовать Button
└── [другие компоненты]        [ПРОВЕРИТЬ] - заменить импорты
```

**Изменения:**
```vue
<!-- Было -->
<PrimaryButton>Submit</PrimaryButton>
<DangerButton>Delete</DangerButton>

<!-- Стало -->
<Button variant="primary">Submit</Button>
<Button variant="danger">Delete</Button>
```

**Приоритет:** Высокий  
**Оценка:** 2-3 часа

---

### 2. Замена прямых вызовов axios на useApi

**Проблема:**
- Прямые вызовы `axios.get/post/patch/delete` вместо `useApi`
- Дублирование заголовков и обработки ошибок
- Непоследовательная обработка ошибок
- **Нарушение принципа переиспользования логики через composables** (Vue.js best practice)

**Файлы с прямыми вызовами axios:**
```
resources/js/Pages/Devices/Show.vue          [3 места] - axios.post, axios.get
resources/js/Pages/Devices/Add.vue           [4 места] - axios.get, axios.patch
resources/js/Components/NodeConfigModal.vue  [2 места] - axios.get, axios.post
resources/js/Pages/Setup/Wizard.vue          [1 место] - axios.get
resources/js/Components/ZoneSimulationModal.vue [axios.post]
resources/js/Components/AttachRecipeModal.vue   [axios.get, axios.post]
resources/js/Components/AttachNodesModal.vue    [axios.get, axios.patch]
resources/js/Pages/Admin/Recipes.vue            [axios.post]
```

**Решение:**
- Заменить все прямые вызовы на `useApi` composable
- Унифицировать обработку ошибок через `useErrorHandler`

**Пример изменения:**
```typescript
// Было
const response = await axios.post(`/api/nodes/${device.value.id}/commands`, {
  type: 'restart',
  params: {},
}, {
  headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
})

// Стало
const { post } = useApi(showToast)
const response = await post(`/nodes/${device.value.id}/commands`, {
  type: 'restart',
  params: {},
})
```

**Приоритет:** Высокий  
**Оценка:** 3-4 часа  
**Vue.js Best Practice:** Переиспользование логики через composables согласно [Composition API guide](https://vuejs.org/guide/reusability/composables.html)

---

### 3. Создание useLoading composable

**Проблема:**
- Дублирование `const loading = ref(false)` в каждом компоненте
- Разные паттерны управления loading состоянием

**Решение:**
Создать `composables/useLoading.ts`:

```typescript
export function useLoading(initialValue = false) {
  const loading = ref(initialValue)
  const isLoading = computed(() => loading.value)
  
  function setLoading(value: boolean) {
    loading.value = value
  }
  
  async function withLoading<T>(fn: () => Promise<T>): Promise<T> {
    loading.value = true
    try {
      return await fn()
    } finally {
      loading.value = false
    }
  }
  
  return {
    loading,
    isLoading,
    setLoading,
    withLoading,
  }
}
```

**Файлы для рефакторинга (14 файлов):**
```
resources/js/Components/AttachNodesModal.vue
resources/js/Components/AttachRecipeModal.vue
resources/js/Components/NodeConfigModal.vue
resources/js/Components/NodeLifecycleTransition.vue
resources/js/Components/PidLogsTable.vue
resources/js/Components/ZoneComparisonModal.vue
resources/js/Components/ZoneSimulationModal.vue
resources/js/composables/useCommands.ts
resources/js/composables/useNodeLifecycle.ts
resources/js/composables/usePidConfig.ts
resources/js/composables/useTelemetry.ts
resources/js/composables/useZones.ts
resources/js/Pages/Devices/Add.vue
resources/js/Pages/Greenhouses/Create.vue
```

**Приоритет:** Средний  
**Оценка:** 2-3 часа

---

### 4. Унификация обработки ошибок

**Проблема:**
- Разная логика обработки ошибок в разных компонентах
- Дублирование try-catch блоков
- Непоследовательное извлечение сообщений об ошибках

**Решение:**
- Использовать `useErrorHandler` везде
- Создать хелперы для типичных сценариев

**Файлы для рефакторинга:**
```
Pages/Devices/Show.vue          [3 места]
Pages/Devices/Add.vue           [4 места]
Components/NodeConfigModal.vue  [2 места]
```

**Пример изменения:**
```typescript
// Было
try {
  const response = await axios.post(...)
} catch (err) {
  logger.error('[Component] Error:', err)
  let errorMsg = 'Неизвестная ошибка'
  if (err && err.response && err.response.data && err.response.data.message) {
    errorMsg = err.response.data.message
  }
  showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
}

// Стало
const { handleError } = useErrorHandler(showToast)
try {
  const response = await post(...)
} catch (err) {
  handleError(err, { action: 'restart device' })
}
```

**Приоритет:** Высокий  
**Оценка:** 2-3 часа

---

### 5. Вынос readBooleanEnv в utils

**Проблема:**
- Функция `readBooleanEnv` дублируется в `useWebSocket.ts` и `echoClient.ts`

**Решение:**
Создать `utils/env.ts`:

```typescript
export function readBooleanEnv(value: unknown, defaultValue: boolean): boolean {
  if (typeof value === 'string') {
    const normalized = value.toLowerCase().trim()
    if (['true', '1', 'yes', 'on'].includes(normalized)) {
      return true
    }
    if (['false', '0', 'no', 'off'].includes(normalized)) {
      return false
    }
  }
  if (typeof value === 'boolean') {
    return value
  }
  return defaultValue
}
```

**Изменения:**
```
utils/env.ts                    [СОЗДАТЬ]
utils/echoClient.ts             [ИЗМЕНИТЬ] - импортировать из utils/env
composables/useWebSocket.ts     [ИЗМЕНИТЬ] - импортировать из utils/env
```

**Приоритет:** Низкий  
**Оценка:** 30 минут

---

### 6. Унификация модальных окон

**Проблема:**
- Дублирование логики открытия/закрытия модалок
- Повторяющийся код для управления состоянием

**Решение:**
Создать `composables/useModal.ts`:

```typescript
export function useModal(initialValue = false) {
  const isOpen = ref(initialValue)
  
  function open() {
    isOpen.value = true
  }
  
  function close() {
    isOpen.value = false
  }
  
  function toggle() {
    isOpen.value = !isOpen.value
  }
  
  return {
    isOpen,
    open,
    close,
    toggle,
  }
}
```

**Файлы для рефакторинга:**
```
Components/ZoneSimulationModal.vue    [использовать useModal]
Components/AttachNodesModal.vue       [уже использует Modal.vue]
Components/AttachRecipeModal.vue      [уже использует Modal.vue]
Components/NodeConfigModal.vue        [использовать useModal]
Components/ZoneActionModal.vue        [использовать useModal]
Components/ZoneComparisonModal.vue    [использовать useModal]
```

**Приоритет:** Средний  
**Оценка:** 2 часа

---

### 7. Улучшение useForm composable

**Проблема:**
- Работа с Inertia формами не всегда использует `useFormValidation`
- Дублирование логики обработки форм

**Решение:**
Создать расширенный `composables/useInertiaForm.ts`:

```typescript
import { useForm } from '@inertiajs/vue3'
import { useFormValidation } from './useFormValidation'
import { useErrorHandler } from './useErrorHandler'

export function useInertiaForm<T extends Record<string, unknown>>(
  initialData: T,
  showToast?: ToastHandler
) {
  const form = useForm<T>(initialData)
  const validation = useFormValidation(form)
  const { handleError } = useErrorHandler(showToast)
  
  async function submit(
    url: string,
    options?: { method?: 'post' | 'put' | 'patch', onSuccess?: () => void }
  ) {
    try {
      await form[options?.method || 'post'](url, {
        onSuccess: () => {
          options?.onSuccess?.()
          if (showToast) {
            showToast('Сохранено успешно', 'success', 3000)
          }
        },
        onError: (errors) => {
          handleError(new Error('Ошибка валидации'), { errors })
        },
      })
    } catch (err) {
      handleError(err, { action: 'submit form' })
    }
  }
  
  return {
    form,
    ...validation,
    submit,
  }
}
```

**Приоритет:** Средний  
**Оценка:** 2-3 часа

---

### 8. Рефакторинг ZoneSimulationModal

**Проблема:**
- `ZoneSimulationModal.vue` не использует базовый `Modal.vue`
- Дублирует логику модального окна

**Решение:**
- Переписать на использование `Modal.vue`
- Использовать `useModal` для управления состоянием

**Изменения:**
```vue
<!-- Было -->
<template>
  <div v-if="show" class="fixed inset-0 z-50 ...">
    <div class="absolute inset-0 bg-black/70" @click="$emit('close')"></div>
    ...
  </div>
</template>

<!-- Стало -->
<template>
  <Modal :open="isOpen" title="Digital Twin Simulation" @close="close">
    ...
  </Modal>
</template>
```

**Приоритет:** Средний  
**Оценка:** 1 час

---

## 📋 Итоговый план действий

### Этап 1: Критические исправления (4-6 часов)
1. ✅ Замена прямых вызовов axios на useApi (3-4 часа)
2. ✅ Унификация обработки ошибок (2-3 часа)

### Этап 2: Унификация компонентов (3-4 часа)
3. ✅ Удаление дублирующих Button компонентов (2-3 часа)
4. ✅ Рефакторинг ZoneSimulationModal (1 час)

### Этап 3: Composable рефакторинг (4-6 часов)
5. ✅ Создание useLoading composable (2-3 часа)
6. ✅ Создание useModal composable (2 часа)

### Этап 4: Улучшения (3-4 часа)
7. ✅ Вынос readBooleanEnv в utils (30 минут)
8. ✅ Улучшение useForm composable (2-3 часа)

**Общая оценка:** 14-20 часов

---

### 9. Унификация парсинга API ответов

**Проблема:**
- Дублирование логики `response.data?.data || response.data || []`
- Разная обработка пагинации и прямых массивов
- Повторяющийся код проверки `data?.data && Array.isArray(data.data)`

**Файлы с дублированием:**
```
resources/js/Pages/Devices/Add.vue           [3 места]
resources/js/Components/HeaderStatusBar.vue  [1 место]
resources/js/composables/useSystemStatus.ts  [1 место]
resources/js/Components/NodeConfigModal.vue  [1 место]
resources/js/composables/usePidConfig.ts     [3 места]
```

**Решение:**
Создать хелперы в `utils/apiHelpers.ts`:

```typescript
/**
 * Извлекает данные из API ответа, обрабатывая пагинацию
 */
export function extractApiData<T>(response: any): T {
  const data = response?.data?.data || response?.data
  // Обработка пагинации
  if (data?.data && Array.isArray(data.data)) {
    return data.data as T
  }
  // Прямой массив или объект
  if (Array.isArray(data) || (data && typeof data === 'object')) {
    return data as T
  }
  return [] as T
}

/**
 * Извлекает объект из API ответа
 */
export function extractApiObject<T>(response: any): T | null {
  const data = response?.data?.data || response?.data
  return data && typeof data === 'object' ? (data as T) : null
}
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа

---

### 10. Унификация работы с Inertia page props

**Проблема:**
- Дублирование `computed(() => page.props.X || {})` в каждом компоненте
- Повторяющаяся логика извлечения props

**Файлы с дублированием:**
```
resources/js/Pages/Zones/Show.vue       [8 computed props]
resources/js/Pages/Dashboard/Index.vue  [множество computed props]
resources/js/Pages/Devices/Show.vue     [3 computed props]
```

**Решение:**
Создать `composables/usePageProps.ts`:

```typescript
import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'

export function usePageProps<T = Record<string, unknown>>() {
  const page = usePage()
  
  function getProp<K extends keyof T>(key: K, defaultValue?: T[K]): T[K] {
    return computed(() => (page.props[key] as T[K]) || defaultValue)
  }
  
  function getAllProps(): T {
    return computed(() => page.props as T)
  }
  
  return {
    props: page.props as T,
    getProp,
    getAllProps,
  }
}
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 11. Унификация валидации в ZoneActionModal

**Проблема:**
- Дублирование логики валидации для разных типов действий
- Повторяющиеся проверки диапазонов значений
- Можно использовать `useFormValidation`

**Решение:**
- Использовать `useFormValidation.validateNumberRange`
- Вынести правила валидации в конфигурацию

**Пример:**
```typescript
const validationRules = {
  FORCE_IRRIGATION: { duration_sec: { min: 1, max: 3600 } },
  FORCE_PH_CONTROL: { target_ph: { min: 4.0, max: 9.0 } },
  // ...
}

const { validateNumberRange } = useFormValidation(form)
```

**Приоритет:** Средний  
**Оценка:** 1 час

---

### 12. Унификация lifecycle hooks для WebSocket

**Проблема:**
- Дублирование паттерна подписки в `onMounted` и отписки в `onUnmounted`
- Повторяющийся код во всех компонентах с WebSocket

**Файлы с дублированием:**
```
resources/js/Pages/Zones/Show.vue          [onMounted/onUnmounted]
resources/js/Components/HeaderStatusBar.vue [onMounted/onUnmounted]
resources/js/composables/useSystemStatus.ts [onMounted/onUnmounted]
```

**Решение:**
Расширить `useWebSocket` для автоматической очистки:

```typescript
export function useWebSocketAutoCleanup(
  showToast?: ToastHandler,
  componentTag?: string
) {
  const ws = useWebSocket(showToast, componentTag)
  
  onMounted(() => {
    // Подписки уже настроены в useWebSocket
  })
  
  onUnmounted(() => {
    ws.unsubscribeAll()
  })
  
  return ws
}
```

**Приоритет:** Средний  
**Оценка:** 1 час

---

### 13. Унификация computed свойств для фильтрации

**Проблема:**
- Дублирование логики фильтрации списков
- Повторяющиеся computed для `filteredUsers`, `filteredEvents`, и т.д.

**Файлы с дублированием:**
```
resources/js/Pages/Dashboard/Index.vue  [filteredEvents]
resources/js/Pages/Settings/Index.vue   [filteredUsers]
resources/js/Pages/Users/Index.vue      [filteredUsers]
```

**Решение:**
Использовать `usePerformance.useMultiFilter` или создать `useFilteredList`:

```typescript
export function useFilteredList<T>(
  items: Ref<T[]>,
  query: Ref<string>,
  filterFn: (item: T, query: string) => boolean
) {
  return computed(() => {
    if (!query.value) return items.value
    return items.value.filter(item => filterFn(item, query.value))
  })
}
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 14. Унификация стилей статусных индикаторов

**Проблема:**
- Дублирование CSS классов для статусных индикаторов в `HeaderStatusBar.vue`
- Повторяющаяся структура HTML для каждого статуса

**Решение:**
Создать компонент `StatusIndicator.vue`:

```vue
<template>
  <div class="relative group">
    <div :class="statusClasses" />
    <div class="absolute inset-0 animate-ping opacity-75" :class="statusClasses" />
    <span class="text-neutral-400 text-[10px]">{{ label }}</span>
    <!-- Tooltip -->
  </div>
</template>
```

**Приоритет:** Низкий  
**Оценка:** 2 часа

---

### 15. Унификация конфигурации графиков

**Проблема:**
- Дублирование настроек ECharts в разных компонентах
- Повторяющиеся стили для темной темы

**Файлы с дублированием:**
```
resources/js/Components/MiniTelemetryChart.vue
resources/js/Components/ZoneSimulationModal.vue
resources/js/Pages/Zones/ZoneTelemetryChart.vue
```

**Решение:**
Создать `utils/chartConfig.ts`:

```typescript
export const defaultChartTheme = {
  textStyle: { color: '#d1d5db' },
  axisLabel: { color: '#9ca3af' },
  splitLine: { lineStyle: { color: '#374151' } },
  // ...
}

export function createChartOption(base: any) {
  return {
    ...base,
    ...defaultChartTheme,
  }
}
```

**Приоритет:** Низкий  
**Оценка:** 2 часа

---

## 📋 Обновленный итоговый план действий

### Этап 1: Критические исправления (4-6 часов)
1. ✅ Замена прямых вызовов axios на useApi (3-4 часа)
2. ✅ Унификация обработки ошибок (2-3 часа)

### Этап 2: Унификация компонентов (3-4 часа)
3. ✅ Удаление дублирующих Button компонентов (2-3 часа)
4. ✅ Рефакторинг ZoneSimulationModal (1 час)

### Этап 3: Composable рефакторинг (6-8 часов)
5. ✅ Создание useLoading composable (2-3 часа)
6. ✅ Создание useModal composable (2 часа)
7. ✅ Унификация парсинга API ответов (1-2 часа)
8. ✅ Унификация lifecycle hooks для WebSocket (1 час)

### Этап 4: Улучшения (5-7 часов)
9. ✅ Вынос readBooleanEnv в utils (30 минут)
10. ✅ Улучшение useForm composable (2-3 часа)
11. ✅ Унификация валидации в ZoneActionModal (1 час)
12. ✅ Унификация работы с page props (1-2 часа)

### Этап 5: Опциональные улучшения (4-6 часов)
13. ✅ Унификация computed для фильтрации (1-2 часа)
14. ✅ Компонент StatusIndicator (2 часа)
15. ✅ Унификация конфигурации графиков (2 часа)

**Обновленная общая оценка:** 22-31 час

---

### 16. Унификация логики определения статусов

**Проблема:**
- Дублирование проверок `status === 'ok' ? ... : status === 'fail' ? ...`
- Повторяющаяся логика маппинга статусов на варианты Badge
- Дублирование проверок статусов в разных местах

**Файлы с дублированием:**
```
resources/js/composables/useSystemStatus.ts  [множество проверок]
resources/js/Components/ServiceStatusCard.vue [getStatusDotClass, getStatusTextClass]
resources/js/Components/SystemMonitoringModal.vue [getChainStatusClass]
resources/js/Pages/Dashboard/Dashboards/AgronomistDashboard.vue [getPhStatus]
```

**Решение:**
Создать `utils/statusHelpers.ts`:

```typescript
export function getStatusVariant(status: string, statusType?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  // Логика определения variant на основе статуса
}

export function getStatusColor(status: string): string {
  // Возвращает цвет для статуса
}

export function isStatusHealthy(status: string): boolean {
  // Проверка, является ли статус здоровым
}
```

**Приоритет:** Средний  
**Оценка:** 2 часа

---

### 17. Унификация работы с датами

**Проблема:**
- Дублирование `new Date()` создания
- Повторяющееся использование `toLocaleString`, `toLocaleDateString`
- Дублирование логики форматирования дат

**Файлы с дублированием:**
```
resources/js/utils/formatTime.js  [formatTime и formatTimeAgo почти идентичны]
resources/js/Components/MiniTelemetryChart.vue [toLocaleDateString, toLocaleTimeString]
resources/js/Components/MultiSeriesTelemetryChart.vue [toISOString]
resources/js/Pages/Zones/Show.vue [toLocaleString]
```

**Решение:**
- Убрать дублирование между `formatTime` и `formatTimeAgo` (они идентичны)
- Создать `utils/dateHelpers.ts` для работы с датами:

```typescript
export function createDate(dateString: string | Date | null): Date | null
export function formatDateTime(date: Date, format: 'short' | 'long'): string
export function formatDate(date: Date): string
export function formatTimeOnly(date: Date): string
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 18. Унификация цветовых классов для статусов

**Проблема:**
- Дублирование классов `bg-red-400`, `text-red-400`, `border-red-800` и т.д.
- Повторяющаяся логика определения цветов на основе статуса

**Файлы с дублированием:**
```
resources/js/Components/HeaderStatusBar.vue  [множество классов]
resources/js/Components/ServiceStatusCard.vue
resources/js/Components/SystemMonitoringModal.vue
```

**Решение:**
Создать `utils/statusColors.ts`:

```typescript
export const statusColors = {
  success: { bg: 'bg-emerald-400', text: 'text-emerald-400', border: 'border-emerald-800' },
  warning: { bg: 'bg-amber-400', text: 'text-amber-400', border: 'border-amber-800' },
  danger: { bg: 'bg-red-400', text: 'text-red-400', border: 'border-red-800' },
  // ...
}

export function getStatusColors(status: string) {
  // Возвращает цвета для статуса
}
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 19. Унификация проверок типов

**Проблема:**
- Дублирование `typeof value === 'string'`, `Array.isArray()`, `typeof value === 'boolean'`
- Повторяющиеся проверки существования свойств

**Файлы с дублированием:**
```
resources/js/utils/echoClient.ts
resources/js/composables/useWebSocket.ts
resources/js/composables/useSystemStatus.ts
```

**Решение:**
Создать `utils/typeGuards.ts`:

```typescript
export function isString(value: unknown): value is string
export function isArray<T>(value: unknown): value is T[]
export function isObject(value: unknown): value is Record<string, unknown>
export function isNumber(value: unknown): value is number
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 20. Унификация логики экспорта данных

**Проблема:**
- Дублирование логики экспорта в CSV (создание blob, download)
- Повторяющийся код для скачивания файлов

**Решение:**
Создать `utils/exportHelpers.ts`:

```typescript
export function exportToCSV(data: any[], filename: string): void
export function exportToJSON(data: any, filename: string): void
export function downloadBlob(blob: Blob, filename: string): void
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 21. Унификация логики определения метрик статуса

**Проблема:**
- Дублирование логики определения статуса на основе значений (pH, EC, температура)
- Повторяющиеся вычисления "в норме/предупреждение/опасно"

**Файлы с дублированием:**
```
resources/js/Pages/Dashboard/Dashboards/AgronomistDashboard.vue [getPhStatus]
resources/js/Components/MiniTelemetryChart.vue [hasAnomalies]
```

**Решение:**
Создать `utils/metricHelpers.ts`:

```typescript
export function getMetricStatus(
  value: number,
  target: { min: number; max: number },
  tolerance?: number
): 'success' | 'warning' | 'danger'

export function detectAnomalies(values: number[]): boolean
```

**Приоритет:** Низкий  
**Оценка:** 2 часа

---

## 📋 Финальный обновленный план действий

### Этап 1: Критические исправления (4-6 часов)
1. ✅ Замена прямых вызовов axios на useApi (3-4 часа)
2. ✅ Унификация обработки ошибок (2-3 часа)

### Этап 2: Унификация компонентов (3-4 часа)
3. ✅ Удаление дублирующих Button компонентов (2-3 часа)
4. ✅ Рефакторинг ZoneSimulationModal (1 час)

### Этап 3: Composable рефакторинг (6-8 часов)
5. ✅ Создание useLoading composable (2-3 часа)
6. ✅ Создание useModal composable (2 часа)
7. ✅ Унификация парсинга API ответов (1-2 часа)
8. ✅ Унификация lifecycle hooks для WebSocket (1 час)

### Этап 4: Улучшения (5-7 часов)
9. ✅ Вынос readBooleanEnv в utils (30 минут)
10. ✅ Улучшение useForm composable (2-3 часа)
11. ✅ Унификация валидации в ZoneActionModal (1 час)
12. ✅ Унификация работы с page props (1-2 часа)

### Этап 5: Опциональные улучшения (9-13 часов)
13. ✅ Унификация computed для фильтрации (1-2 часа)
14. ✅ Компонент StatusIndicator (2 часа)
15. ✅ Унификация конфигурации графиков (2 часа)
16. ✅ Унификация логики определения статусов (2 часа)
17. ✅ Унификация работы с датами (1-2 часа)
18. ✅ Унификация цветовых классов (1-2 часа)
19. ✅ Унификация проверок типов (1 час)
20. ✅ Унификация экспорта данных (1 час)
21. ✅ Унификация метрик статуса (2 часа)

**Финальная общая оценка:** 27-38 часов

---

### 22. Унификация структуры Pinia stores

**Проблема:**
- Zones, Devices, Recipes stores имеют почти идентичную структуру
- Дублирование методов: `upsert`, `remove`, `clear`, `invalidateCache`, `setLoading`, `setError`
- Дублирование getters: `byId`, `all`, `hasItems`, `count`

**Файлы с дублированием:**
```
resources/js/stores/zones.ts      [254 строки]
resources/js/stores/devices.ts    [302 строки]
resources/js/stores/recipes.ts    [168 строк]
```

**Решение:**
Создать базовый composable или factory для stores:

```typescript
// utils/createStoreFactory.ts
export function createBaseStore<T extends { id: number }>(
  name: string,
  options: StoreOptions<T>
) {
  // Общая логика для всех stores
}
```

**Приоритет:** Средний  
**Оценка:** 3-4 часа

---

### 23. Унификация пустых состояний

**Проблема:**
- Дублирование текстов "Нет данных", "Загрузка...", "Пусто", "Ничего не найдено"
- Повторяющаяся структура пустых состояний

**Файлы с дублированием:**
```
resources/js/Components/LoadingState.vue
resources/js/Components/CommandPalette.vue [множество пустых состояний]
resources/js/Components/MiniTelemetryChart.vue
resources/js/Pages/Dashboard/Index.vue
resources/js/Pages/Alerts/Index.vue
```

**Решение:**
Создать компонент `EmptyState.vue`:

```vue
<template>
  <div :class="containerClass">
    <div v-if="icon" class="text-4xl mb-2">{{ icon }}</div>
    <div :class="textClass">{{ message }}</div>
    <div v-if="description" :class="descriptionClass">{{ description }}</div>
  </div>
</template>
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 24. Унификация тернарных операторов для классов

**Проблема:**
- Множественные `:class="condition ? 'class1' : 'class2'"`
- Дублирование логики условных классов

**Файлы с дублированием:**
```
resources/js/Components/HeaderStatusBar.vue  [множество тернарных операторов]
resources/js/Components/ServiceStatusCard.vue
resources/js/Pages/Zones/Index.vue
resources/js/Components/ZoneTargets.vue
```

**Решение:**
Создать composable `useConditionalClasses`:

```typescript
export function useConditionalClasses() {
  function classIf(condition: boolean, classes: string): string {
    return condition ? classes : ''
  }
  
  function classIfElse(
    condition: boolean,
    trueClasses: string,
    falseClasses: string
  ): string {
    return condition ? trueClasses : falseClasses
  }
  
  return { classIf, classIfElse }
}
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 25. Унификация форматирования значений

**Проблема:**
- Дублирование `formatValue`, `formatTelemetryValue`
- Повторяющаяся логика форматирования pH, EC, температуры, влажности

**Файлы с дублированием:**
```
resources/js/Pages/Zones/ZoneCard.vue      [formatValue]
resources/js/Components/ZoneTargets.vue    [formatTelemetryValue]
resources/js/Components/MiniTelemetryChart.vue [formatValue]
```

**Решение:**
Создать `utils/formatHelpers.ts`:

```typescript
export function formatTelemetryValue(
  value: number | null | undefined,
  type: 'ph' | 'ec' | 'temp' | 'humidity'
): string

export function formatMetric(value: number, unit: string, decimals?: number): string
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа

---

### 26. Унификация паттернов .map().filter()

**Проблема:**
- Дублирование паттернов `.map().filter()` в stores и компонентах
- Повторяющаяся логика фильтрации и трансформации

**Файлы с дублированием:**
```
resources/js/stores/zones.ts      [множество .map().filter()]
resources/js/stores/devices.ts    [множество .map().filter()]
resources/js/stores/recipes.ts    [множество .map().filter()]
resources/js/Pages/Dashboard/Index.vue
```

**Решение:**
Создать утилиты в `utils/arrayHelpers.ts`:

```typescript
export function mapAndFilter<T, R>(
  items: T[],
  mapper: (item: T) => R,
  filter?: (item: T) => boolean
): R[]

export function filterMap<T, R>(
  items: T[],
  filterFn: (item: T) => boolean,
  mapper: (item: T) => R
): R[]
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 27. Унификация обработки setTimeout в тестах

**Проблема:**
- Множественные `setTimeout(resolve, 100)` в тестах
- Дублирование логики ожидания

**Файлы с дублированием:**
```
resources/js/Pages/Recipes/__tests__/Edit.spec.ts
resources/js/Pages/Zones/__tests__/Show.websocket.spec.ts
resources/js/Components/__tests__/HeaderStatusBar.websocket.spec.ts
```

**Решение:**
Создать тестовые утилиты:

```typescript
// __tests__/helpers/testUtils.ts
export function wait(ms: number): Promise<void>
export function waitForNextTick(): Promise<void>
```

**Приоритет:** Низкий  
**Оценка:** 30 минут

---

### 28. Унификация логики определения вариантов Badge

**Проблема:**
- Дублирование логики `getStatusVariant`, `getLifecycleVariant`
- Повторяющиеся switch/case для определения variant

**Файлы с дублированием:**
```
resources/js/Components/NodeLifecycleBadge.vue
resources/js/Pages/Devices/Add.vue
resources/js/Pages/Dashboard/Index.vue
```

**Решение:**
Создать `utils/badgeHelpers.ts`:

```typescript
export function getStatusVariant(status: string): BadgeVariant
export function getLifecycleVariant(state: string): BadgeVariant
export function getZoneStatusVariant(status: string): BadgeVariant
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 29. Унификация проверок существования массивов

**Проблема:**
- Дублирование `Array.isArray(items) && items.length > 0`
- Повторяющиеся проверки на пустоту

**Файлы с дублированием:**
```
resources/js/stores/zones.ts
resources/js/stores/devices.ts
resources/js/stores/recipes.ts
resources/js/Pages/Dashboard/Index.vue
```

**Решение:**
Создать утилиты в `utils/arrayHelpers.ts`:

```typescript
export function isNonEmptyArray<T>(value: unknown): value is T[]
export function isEmptyArray(value: unknown): boolean
```

**Приоритет:** Низкий  
**Оценка:** 30 минут

---

### 30. Унификация обработки submit форм

**Проблема:**
- Дублирование `@submit.prevent="submit"` во всех формах Auth
- Повторяющаяся логика обработки форм

**Файлы с дублированием:**
```
resources/js/Pages/Auth/Login.vue
resources/js/Pages/Auth/Register.vue
resources/js/Pages/Auth/ForgotPassword.vue
resources/js/Pages/Auth/ResetPassword.vue
resources/js/Pages/Auth/ConfirmPassword.vue
resources/js/Pages/Auth/VerifyEmail.vue
```

**Решение:**
Использовать улучшенный `useInertiaForm` (см. пункт 7)

**Приоритет:** Средний  
**Оценка:** 1 час (уже включено в пункт 7)

---

## 📋 Финальный обновленный план действий

### Этап 1: Критические исправления (4-6 часов)
1. ✅ Замена прямых вызовов axios на useApi (3-4 часа)
2. ✅ Унификация обработки ошибок (2-3 часа)

### Этап 2: Унификация компонентов (3-4 часа)
3. ✅ Удаление дублирующих Button компонентов (2-3 часа)
4. ✅ Рефакторинг ZoneSimulationModal (1 час)

### Этап 3: Composable рефакторинг (6-8 часов)
5. ✅ Создание useLoading composable (2-3 часа)
6. ✅ Создание useModal composable (2 часа)
7. ✅ Унификация парсинга API ответов (1-2 часа)
8. ✅ Унификация lifecycle hooks для WebSocket (1 час)

### Этап 4: Улучшения (5-7 часов)
9. ✅ Вынос readBooleanEnv в utils (30 минут)
10. ✅ Улучшение useForm composable (2-3 часа)
11. ✅ Унификация валидации в ZoneActionModal (1 час)
12. ✅ Унификация работы с page props (1-2 часа)

### Этап 5: Опциональные улучшения (13-18 часов)
13. ✅ Унификация computed для фильтрации (1-2 часа)
14. ✅ Компонент StatusIndicator (2 часа)
15. ✅ Унификация конфигурации графиков (2 часа)
16. ✅ Унификация логики определения статусов (2 часа)
17. ✅ Унификация работы с датами (1-2 часа)
18. ✅ Унификация цветовых классов (1-2 часа)
19. ✅ Унификация проверок типов (1 час)
20. ✅ Унификация экспорта данных (1 час)
21. ✅ Унификация метрик статуса (2 часа)
22. ✅ Унификация структуры Pinia stores (3-4 часа) ⭐ **НОВЫЙ**
23. ✅ Унификация пустых состояний (1-2 часа) ⭐ **НОВЫЙ**
24. ✅ Унификация тернарных операторов для классов (1 час) ⭐ **НОВЫЙ**
25. ✅ Унификация форматирования значений (1-2 часа) ⭐ **НОВЫЙ**
26. ✅ Унификация паттернов .map().filter() (1 час) ⭐ **НОВЫЙ**
27. ✅ Унификация setTimeout в тестах (30 минут) ⭐ **НОВЫЙ**
28. ✅ Унификация логики Badge вариантов (1 час) ⭐ **НОВЫЙ**
29. ✅ Унификация проверок массивов (30 минут) ⭐ **НОВЫЙ**

**Финальная общая оценка:** 31-43 часа

---

### 31. Унификация работы с localStorage/sessionStorage

**Проблема:**
- Дублирование логики загрузки/сохранения в localStorage/sessionStorage
- Повторяющиеся паттерны `getItem`, `setItem`, `removeItem` с обработкой ошибок

**Файлы с дублированием:**
```
resources/js/composables/useFavorites.ts       [loadFromStorage, saveToStorage]
resources/js/composables/useHistory.ts         [loadFromStorage, saveToStorage]
resources/js/Pages/Dashboard/Index.vue         [прямое использование localStorage]
resources/js/Components/CommandPalette.vue     [прямое использование localStorage]
resources/js/composables/__tests__/useTelemetry.cache.spec.ts
```

**Решение:**
Создать утилиту `utils/storage.ts`:

```typescript
export function storageGet<T>(key: string, defaultValue: T): T
export function storageSet<T>(key: string, value: T): void
export function storageRemove(key: string): void
export function storageClear(): void
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа

---

### 32. Унификация валидации диапазонов (magic numbers)

**Проблема:**
- Магические числа для валидации: `3600`, `4.0`, `9.0`, `10`, `35`, `30`, `90`
- Дублирование проверок диапазонов в ZoneActionModal и других компонентах

**Файлы с дублированием:**
```
resources/js/Components/ZoneActionModal.vue        [множество проверок min/max]
resources/js/Components/ZoneSimulationModal.vue    [проверки диапазонов]
resources/js/composables/useFormValidation.ts      [validateNumberRange]
```

**Решение:**
Создать константы и использовать их:

```typescript
// constants/validation.ts
export const VALIDATION_RANGES = {
  IRRIGATION_DURATION: { min: 1, max: 3600 },
  PH: { min: 4.0, max: 9.0 },
  EC: { min: 0.1, max: 10.0 },
  TEMPERATURE: { min: 10, max: 35 },
  HUMIDITY: { min: 30, max: 90 },
  LIGHT_INTENSITY: { min: 0, max: 100 },
  LIGHT_DURATION: { min: 0.5, max: 24 },
} as const
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа

---

### 33. Унификация сортировки массивов

**Проблема:**
- Дублирование паттернов `.sort((a, b) => a - b)` и `.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))`

**Файлы с дублированием:**
```
resources/js/Pages/Dashboard/Index.vue
resources/js/Components/RoleBasedNavigation.vue
resources/js/Components/ZoneComparisonModal.vue
resources/js/Components/MultiSeriesTelemetryChart.vue
resources/js/composables/useTelemetry.ts
resources/js/Pages/Recipes/Show.vue
resources/js/Pages/Recipes/Edit.vue
```

**Решение:**
Создать утилиты в `utils/arrayHelpers.ts`:

```typescript
export function sortByNumber<T>(items: T[], getter: (item: T) => number): T[]
export function sortByTimestamp<T>(items: T[], getter: (item: T) => number): T[]
export function sortByOrder<T extends { order?: number }>(items: T[]): T[]
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 34. Унификация строковых операций

**Проблема:**
- Дублирование `.toLowerCase()`, `.trim()`, `.replace()` паттернов

**Файлы с дублированием:**
```
resources/js/composables/useWebSocket.ts
resources/js/utils/echoClient.ts
resources/js/Pages/Settings/Index.vue
resources/js/Pages/Users/Index.vue
resources/js/Pages/Devices/Show.vue
```

**Решение:**
Создать утилиты в `utils/stringHelpers.ts`:

```typescript
export function normalizeString(value: unknown, defaultValue: string = ''): string
export function fuzzyMatch(str: string, query: string): boolean
export function truncate(str: string, maxLength: number): string
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 35. Унификация построения URL/роутов

**Проблема:**
- Дублирование шаблонных строк `\`/zones/${id}\``, `\`/devices/${id}\``

**Файлы с дублированием:**
```
resources/js/Pages/Dashboard/Index.vue          [множество `href="/zones/${id}"`]
resources/js/Pages/Devices/Show.vue             [множество `href="/zones/${id}"`]
resources/js/Pages/Devices/Index.vue
resources/js/Components/ZonesHeatmap.vue
resources/js/Components/GreenhouseStatusCard.vue
resources/js/Pages/Dashboard/Dashboards/*.vue
```

**Решение:**
Улучшить `route.ts` helper или создать URL builder:

```typescript
// utils/routes.ts
export const routes = {
  zones: {
    index: '/zones',
    show: (id: number) => `/zones/${id}`,
    create: '/zones/create',
  },
  devices: {
    index: '/devices',
    show: (id: number | string) => `/devices/${id}`,
  },
  // ...
} as const
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа

---

### 36. Унификация watch паттернов

**Проблема:**
- Дублирование логики watch для инициализации, синхронизации состояния

**Файлы с дублированием:**
```
resources/js/Components/HeaderStatusBar.vue      [watch(dashboardData)]
resources/js/Pages/Zones/Show.vue                [watch(zone)]
resources/js/Pages/Dashboard/Index.vue           [множество watch]
resources/js/Pages/Devices/Show.vue              [watch(device)]
resources/js/Components/ZoneComparisonModal.vue
resources/js/Components/NodeConfigModal.vue
```

**Решение:**
Создать composable `useWatchers` для общих паттернов:

```typescript
export function useWatchers() {
  function watchAndSync<T>(
    source: Ref<T>,
    target: Ref<T>,
    immediate?: boolean
  ): () => void
  // Другие общие паттерны
}
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 37. Унификация nextTick в тестах

**Проблема:**
- Множественные `await nextTick()` и `await wrapper.vm.$nextTick()`

**Файлы с дублированием:**
```
resources/js/Pages/Zones/__tests__/Show.websocket.spec.ts
resources/js/Components/__tests__/HeaderStatusBar.websocket.spec.ts
resources/js/Components/__tests__/ZoneActionModal.validation.spec.ts
```

**Решение:**
Создать тестовые утилиты (уже частично в п.27, расширить):

```typescript
// __tests__/helpers/testUtils.ts
export async function waitForNextTick(): Promise<void>
export async function waitForRendered(component: any): Promise<void>
```

**Приоритет:** Низкий  
**Оценка:** 30 минут (расширение п.27)

---

### 38. Унификация сообщений об ошибках

**Проблема:**
- Дублирование текстов ошибок: "Ошибка сети", "Требуется авторизация", "Доступ запрещен"

**Файлы с дублированием:**
```
resources/js/composables/useErrorHandler.ts      [множество сообщений]
resources/js/Components/ErrorBoundary.vue        ["Произошла ошибка"]
resources/js/Components/InputError.vue
resources/js/Pages/Zones/__tests__/Show.websocket.spec.ts
```

**Решение:**
Создать `constants/messages.ts`:

```typescript
export const ERROR_MESSAGES = {
  NETWORK: 'Ошибка сети. Проверьте подключение.',
  UNAUTHORIZED: 'Требуется авторизация',
  FORBIDDEN: 'Доступ запрещен',
  NOT_FOUND: 'Ресурс не найден',
  SERVER_ERROR: 'Ошибка сервера. Попробуйте позже.',
  VALIDATION: 'Ошибка валидации. Проверьте введенные данные.',
} as const
```

**Приоритет:** Низкий  
**Оценка:** 1 час

---

### 39. Замена console.* на logger

**Проблема:**
- Прямое использование `console.log`, `console.error`, `console.warn` вместо `logger`
- **Нарушение единообразия логирования** в приложении

**Файлы с дублированием:**
```
resources/js/Pages/Zones/Show.vue                [fallback на console.*]
resources/js/bootstrap.js                        [console.error]
resources/js/app.js                              [console.error, console.warn]
resources/js/utils/logger.ts                     [внутренние console.* - нормально]
resources/js/Components/ZoneComparisonModal.vue  [console.error]
```

**Решение:**
Заменить все `console.*` на `logger.*` (кроме самого logger.ts):

```typescript
// Заменить console.error на logger.error
// Заменить console.warn на logger.warn
// Заменить console.log на logger.info
```

**Приоритет:** Низкий  
**Оценка:** 1 час  
**Vue.js Best Practice:** Централизованное логирование через composables/utilities

---

### 40. Проверка использования Composition API паттернов ⭐ **НОВЫЙ**

**Проблема:**
- Некоторые компоненты могут использовать устаревшие паттерны
- Не все компоненты используют `<script setup lang="ts">`
- Отсутствие типизации в некоторых местах

**Согласно [Vue.js документации](https://vuejs.org/guide/introduction.html):**
> "For production use: Go with Composition API + Single-File Components if you plan to build full applications with Vue."

**Решение:**
1. Проверить все компоненты на использование `<script setup lang="ts">`
2. Убедиться что используются composables вместо дублирования логики
3. Проверить использование TypeScript типов для props и emits

**Файлы для проверки:**
```
resources/js/Components/ZoneSimulationModal.vue  [<script setup> без lang="ts"]
resources/js/Pages/Admin/Recipes.vue             [проверить типизацию props]
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа  
**Vue.js Best Practice:** См. [Composition API FAQ](https://vuejs.org/guide/extras/composition-api-faq.html)

---

### 41. Оптимизация использования router.reload() с `only` ⭐ **НОВЫЙ**

**Проблема:**
- Не везде используется опция `only` для partial reloads
- Отсутствие `preserveScroll` в некоторых местах
- Прямые вызовы `router.visit()` вместо `Link` компонента где возможно

**Согласно лучшим практикам Inertia.js:**
- Использовать `only` для загрузки только необходимых props (уменьшает нагрузку)
- Использовать `preserveScroll` для лучшего UX
- Использовать `preserveState` для сохранения локального состояния компонента

**Файлы для проверки:**
```
resources/js/Pages/Zones/Show.vue          [router.reload без only в некоторых местах]
resources/js/Pages/Dashboard/Index.vue     [router.visit вместо Link]
resources/js/Pages/Plants/Index.vue        [router.delete без preserveScroll]
```

**Решение:**
1. Всегда использовать `only` для partial reloads:
```typescript
// Было
router.reload()

// Стало
router.reload({ only: ['zone', 'devices'], preserveScroll: true })
```

2. Использовать `preserveScroll` для действий не меняющих позицию:
```typescript
router.reload({ only: ['zone'], preserveScroll: true })
```

3. Использовать `preserveState` для сохранения локального состояния:
```typescript
router.reload({ only: ['zone'], preserveState: true })
```

**Приоритет:** Средний  
**Оценка:** 1-2 часа  
**Inertia.js Best Practice:** Оптимизация partial reloads

---

### 42. Унификация обработки Inertia форм callbacks ⭐ **НОВЫЙ**

**Проблема:**
- Непоследовательное использование `onSuccess`, `onError`, `onFinish`
- Отсутствие единообразия в обработке ошибок форм
- Дублирование логики reset формы после submit

**Файлы для проверки:**
```
resources/js/Pages/Auth/*.vue              [используют onFinish для reset]
resources/js/Pages/Profile/*.vue           [используют onSuccess для reset]
resources/js/Pages/Recipes/Edit.vue        [собственная обработка ошибок]
```

**Решение:**
Создать composable `useInertiaForm` для унификации:

```typescript
export function useInertiaForm<T extends Record<string, unknown>>(
  initialData: T,
  options?: {
    onSuccess?: () => void
    onError?: (errors: Record<string, string>) => void
    resetOnSuccess?: boolean
    preserveScroll?: boolean
  }
) {
  const form = useForm(initialData)
  
  function submit(method: string, url: string, data?: Partial<T>) {
    return form[method](url, {
      preserveScroll: options?.preserveScroll ?? true,
      onSuccess: () => {
        if (options?.resetOnSuccess) {
          form.reset()
        }
        options?.onSuccess?.()
      },
      onError: (errors) => {
        options?.onError?.(errors)
      },
      onFinish: () => {
        // Общая логика после завершения
      }
    })
  }
  
  return { form, submit }
}
```

**Приоритет:** Средний  
**Оценка:** 2-3 часа  
**Inertia.js Best Practice:** Единообразная обработка форм

---

### 43. Использование Link компонента вместо router.visit() ⭐ **НОВЫЙ**

**Проблема:**
- Прямое использование `router.visit()` для навигации вместо `Link` компонента
- Упущенные возможности оптимизации (prefetching)

**Согласно лучшим практикам Inertia.js:**
> Используйте компонент `Link` вместо `router.visit()` для навигации, так как он обеспечивает prefetching и лучшую производительность.

**Файлы для проверки:**
```
resources/js/Pages/Dashboard/Index.vue     [router.visit для переходов к зонам]
resources/js/composables/useKeyboardShortcuts.ts [router.visit для навигации]
```

**Решение:**
1. Заменить `router.visit()` на `Link` где возможно:
```vue
<!-- Было -->
<button @click="router.visit(`/zones/${zone.id}`)">View Zone</button>

<!-- Стало -->
<Link :href="`/zones/${zone.id}`">
  <Button>View Zone</Button>
</Link>
```

2. Для программной навигации (например, в composables) оставить `router.visit()`, но добавить опции:
```typescript
router.visit(url, {
  preserveScroll: true,
  only: ['zone'], // если нужно
})
```

**Приоритет:** Низкий  
**Оценка:** 1-2 часа  
**Inertia.js Best Practice:** Использование Link компонента для навигации

---

## 📋 Финальный обновленный план действий

### Этап 1: Критические исправления (4-6 часов)
1. ✅ Замена прямых вызовов axios на useApi (3-4 часа)
2. ✅ Унификация обработки ошибок (2-3 часа)

### Этап 2: Унификация компонентов (3-4 часа)
3. ✅ Удаление дублирующих Button компонентов (2-3 часа)
4. ✅ Рефакторинг ZoneSimulationModal (1 час)

### Этап 3: Composable рефакторинг (6-8 часов)
5. ✅ Создание useLoading composable (2-3 часа)
6. ✅ Создание useModal composable (2 часа)
7. ✅ Унификация парсинга API ответов (1-2 часа)
8. ✅ Унификация lifecycle hooks для WebSocket (1 час)

### Этап 4: Улучшения (5-7 часов)
9. ✅ Вынос readBooleanEnv в utils (30 минут)
10. ✅ Улучшение useForm composable (2-3 часа)
11. ✅ Унификация валидации в ZoneActionModal (1 час)
12. ✅ Унификация работы с page props (1-2 часа)

### Этап 5: Опциональные улучшения (20-28 часов)
13-29. (см. предыдущие пункты)
30. ✅ Унификация работы с localStorage (1-2 часа) ⭐ **НОВЫЙ**
31. ✅ Унификация валидации диапазонов (1-2 часа) ⭐ **НОВЫЙ**
32. ✅ Унификация сортировки массивов (1 час) ⭐ **НОВЫЙ**
33. ✅ Унификация строковых операций (1 час) ⭐ **НОВЫЙ**
34. ✅ Унификация построения URL (1-2 часа) ⭐ **НОВЫЙ**
35. ✅ Унификация watch паттернов (1 час) ⭐ **НОВЫЙ**
36. ✅ Унификация nextTick в тестах (30 минут) ⭐ **НОВЫЙ** (расширение п.27)
37. ✅ Унификация сообщений об ошибках (1 час) ⭐ **НОВЫЙ**
38. ✅ Замена console.* на logger (1 час) ⭐ **НОВЫЙ**
39. ✅ Оптимизация router.reload() с `only` (1-2 часа) ⭐ **НОВЫЙ** (Inertia.js)
40. ✅ Унификация обработки Inertia форм callbacks (2-3 часа) ⭐ **НОВЫЙ** (Inertia.js)
41. ✅ Использование Link вместо router.visit() (1-2 часа) ⭐ **НОВЫЙ** (Inertia.js)

**Финальная общая оценка:** 43-60 часов (включая миграцию на Composition API и оптимизацию Inertia.js)

### Резюме по этапам:
- **Этап 0:** Миграция на Composition API (2-4 часа)
- **Этап 1:** Критические исправления (4-6 часов)
- **Этап 2:** Унификация компонентов (3-4 часа)
- **Этап 3:** Composable рефакторинг (6-8 часов)
- **Этап 4:** Улучшения (5-7 часов)
- **Этап 5:** Опциональные улучшения (20-28 часов)

---

## 📚 Ссылки на документацию

### Vue.js:
- [Introduction - Composition API](https://vuejs.org/guide/introduction.html#composition-api) - Рекомендации по выбору API стиля
- [Composables Guide](https://vuejs.org/guide/reusability/composables.html) - Паттерны переиспользования логики
- [Single-File Components](https://vuejs.org/guide/scaling-up/sfc.html) - Рекомендуемый формат компонентов
- [TypeScript Support](https://vuejs.org/guide/typescript/overview.html) - Типизация компонентов
- [Performance Best Practices](https://vuejs.org/guide/best-practices/performance.html) - Оптимизация производительности

### Inertia.js:
- [Inertia.js Documentation](https://inertiajs.com/) - Официальная документация
- [Partial Reloads](https://inertiajs.com/partial-reloads) - Оптимизация с опцией `only`
- [Preserving State](https://inertiajs.com/preserving-state) - Сохранение состояния компонента
- [Form Helper](https://inertiajs.com/forms) - Работа с формами
- [Link Component](https://inertiajs.com/links) - Использование Link для навигации

---

## 📝 Чеклист рефакторинга

### Перед началом:
- [ ] Создать ветку для рефакторинга
- [ ] Убедиться, что все тесты проходят
- [ ] Создать бэкап текущего состояния

### После каждого этапа:
- [ ] Запустить все тесты
- [ ] Проверить линтер
- [ ] Проверить типы TypeScript
- [ ] Протестировать вручную основные сценарии

### После завершения:
- [ ] Обновить документацию
- [ ] Обновить примеры кода
- [ ] Провести code review
- [ ] Замерять метрики (размер bundle, количество строк кода)

---

## 🎯 Ожидаемые результаты

### Количественные метрики:
- **Удаление строк кода:** ~800-1200 строк
- **Удаление файлов:** 3 файла (Button компоненты)
- **Новые composables:** 6-8 файлов
- **Новые utils:** 2-3 файла
- **Единообразие:** 100% использование useApi, useErrorHandler, useLoading
- **Файлов для рефакторинга:**
  - С прямыми вызовами axios: 6 файлов
  - С дублированием loading: 14 файлов
  - С парсингом response.data?.data: 7 файлов
  - С computed(() => page.props): 4 файла
  - С onMounted/onUnmounted: 30 файлов (частично)

### Качественные улучшения:
- ✅ Единообразный код
- ✅ Легче поддерживать
- ✅ Меньше багов из-за дублирования
- ✅ Лучшая типизация
- ✅ Переиспользуемость логики

---

## 📚 Связанные файлы

### Новые файлы:
- `composables/useLoading.ts`
- `composables/useModal.ts`
- `composables/useInertiaForm.ts`
- `composables/usePageProps.ts`
- `composables/useWebSocketAutoCleanup.ts`
- `composables/useFilteredList.ts`
- `utils/env.ts`
- `utils/apiHelpers.ts`
- `utils/chartConfig.ts`
- `Components/StatusIndicator.vue`

### Файлы для удаления:
- `Components/PrimaryButton.vue`
- `Components/SecondaryButton.vue`
- `Components/DangerButton.vue`

### Файлы для изменения:
- `Pages/Devices/Show.vue`
- `Pages/Devices/Add.vue`
- `Components/NodeConfigModal.vue`
- `Pages/Setup/Wizard.vue`
- `utils/echoClient.ts`
- `composables/useWebSocket.ts`
- [и другие из списка выше]

---

**Дата создания:** 2025-11-27  
**Дата завершения:** 2025-01-27  
**Статус:** ✅ **РЕФАКТОРИНГ ЗАВЕРШЕН**  
**Основано на:** [Vue.js Official Documentation](https://vuejs.org/guide/introduction.html)

---

## ✅ Статус выполнения

**Все задачи плана выполнены на 100%**

- ✅ Этап 1: Критические исправления (4-6 часов)
- ✅ Этап 2: Унификация компонентов (3-4 часа)
- ✅ Этап 3: Composable рефакторинг (6-8 часов)
- ✅ Этап 4: Улучшения (5-7 часов)
- ✅ Этап 5: Опциональные улучшения (20-28 часов)

**Итого:** Все 41 задача из плана выполнена.

