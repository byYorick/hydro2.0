/**
 * Composable для оптимизации производительности компонентов
 */
import { computed, type Ref, type ComputedRef } from 'vue'

/**
 * Мемоизирует результат функции фильтрации
 * Используется для оптимизации фильтрации больших списков
 */
export function useMemoizedFilter<T>(
  items: Ref<T[]> | ComputedRef<T[]>,
  filterFn: (item: T) => boolean
): ComputedRef<T[]> {
  return computed(() => {
    return items.value.filter(filterFn)
  })
}

/**
 * Создает мемоизированную версию строки в нижнем регистре
 * Полезно для оптимизации поиска
 */
export function useLowercaseQuery(query: Ref<string>): ComputedRef<string> {
  return computed(() => query.value.toLowerCase())
}

/**
 * Оптимизированная фильтрация с несколькими условиями
 */
export function useMultiFilter<T>(
  items: Ref<T[]> | ComputedRef<T[]>,
  filters: Record<string, Ref<unknown> | ComputedRef<unknown>>,
  filterFn: (item: T, filters: Record<string, unknown>) => boolean
): ComputedRef<T[]> {
  const filterValues = computed(() => {
    const values: Record<string, unknown> = {}
    for (const [key, filter] of Object.entries(filters)) {
      values[key] = filter.value
    }
    return values
  })

  return computed(() => {
    const values = filterValues.value
    const hasActiveFilters = Object.values(values).some(v => v !== '' && v !== null && v !== undefined)
    
    if (!hasActiveFilters) {
      return items.value // Если нет активных фильтров, возвращаем все элементы
    }
    
    return items.value.filter(item => filterFn(item, values))
  })
}

/**
 * Дебаунс для оптимизации частых обновлений
 */
export function useDebounce<T>(value: Ref<T>, delay: number = 300): ComputedRef<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  const debounced = computed({
    get: () => value.value,
    set: (newValue: T) => {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
      timeoutId = setTimeout(() => {
        value.value = newValue
      }, delay)
    }
  })
  
  return debounced
}

