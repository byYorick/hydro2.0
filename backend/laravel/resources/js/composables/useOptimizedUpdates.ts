import { ref, watch, computed, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { DEBOUNCE_DELAY } from '@/constants/timeouts'

/**
 * Composable для оптимизации частых обновлений
 * Использует debounce и batch updates для производительности
 */

export interface BatchUpdateConfig {
  debounceMs?: number
  maxBatchSize?: number
  maxWaitMs?: number
}

const defaultConfig: Required<BatchUpdateConfig> = {
  debounceMs: 100,
  maxBatchSize: 10,
  maxWaitMs: 500,
}

/**
 * Создает debounced функцию
 */
export function useDebounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  
  return (...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    timeoutId = setTimeout(() => {
      fn(...args)
      timeoutId = null
    }, delay)
  }
}

/**
 * Создает throttled функцию
 */
export function useThrottle<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let lastCall = 0
  
  return (...args: Parameters<T>) => {
    const now = Date.now()
    if (now - lastCall >= delay) {
      lastCall = now
      fn(...args)
    }
  }
}

/**
 * Batch updates для множественных изменений
 * Накапливает обновления и применяет их пакетами
 */
export function useBatchUpdates<T>(
  updateFn: (items: T[]) => void,
  config: BatchUpdateConfig = {}
) {
  const mergedConfig = { ...defaultConfig, ...config }
  const batch: T[] = []
  let batchTimeout: ReturnType<typeof setTimeout> | null = null
  let lastUpdate = Date.now()
  
  const flush = () => {
    if (batch.length > 0) {
      updateFn([...batch])
      batch.length = 0
    }
    if (batchTimeout) {
      clearTimeout(batchTimeout)
      batchTimeout = null
    }
    lastUpdate = Date.now()
  }
  
  const add = (item: T) => {
    batch.push(item)
    
    // Если достигли максимального размера батча, применяем сразу
    if (batch.length >= mergedConfig.maxBatchSize) {
      flush()
      return
    }
    
    // Если прошло слишком много времени с последнего обновления, применяем
    const timeSinceLastUpdate = Date.now() - lastUpdate
    if (timeSinceLastUpdate >= mergedConfig.maxWaitMs) {
      flush()
      return
    }
    
    // Иначе ждем debounce времени
    if (batchTimeout) {
      clearTimeout(batchTimeout)
    }
    batchTimeout = setTimeout(flush, mergedConfig.debounceMs)
  }
  
  const forceFlush = () => {
    flush()
  }
  
  return {
    add,
    flush: forceFlush,
    getBatchSize: () => batch.length,
  }
}

/**
 * Оптимизированный watcher для частых обновлений
 * Использует debounce для уменьшения количества обновлений
 */
export function useOptimizedWatcher<T>(
  source: Ref<T> | (() => T),
  callback: (value: T) => void,
  debounceMs: number = 100
) {
  const debouncedCallback = useDebounce(callback, debounceMs)
  
  if (typeof source === 'function') {
    watch(source, (newValue) => {
      debouncedCallback(newValue)
    }, { immediate: true })
  } else {
    watch(source, (newValue) => {
      debouncedCallback(newValue)
    }, { immediate: true })
  }
}

/**
 * Виртуализация для больших списков
 * Позволяет рендерить только видимые элементы
 */
export interface VirtualListConfig {
  itemHeight: number
  containerHeight: number
  overscan?: number
}

export function useVirtualList<T>(
  items: Ref<T[]>,
  config: VirtualListConfig
) {
  const scrollTop = ref(0)
  const overscan = config.overscan ?? 3
  
  const visibleRange = computed(() => {
    const start = Math.floor(scrollTop.value / config.itemHeight)
    const end = Math.min(
      start + Math.ceil(config.containerHeight / config.itemHeight) + overscan * 2,
      items.value.length
    )
    const startWithOverscan = Math.max(0, start - overscan)
    
    return {
      start: startWithOverscan,
      end,
      total: items.value.length,
    }
  })
  
  const visibleItems = computed(() => {
    const range = visibleRange.value
    return items.value.slice(range.start, range.end).map((item, index) => ({
      item,
      index: range.start + index,
    }))
  })
  
  const totalHeight = computed(() => {
    return items.value.length * config.itemHeight
  })
  
  const offsetY = computed(() => {
    return visibleRange.value.start * config.itemHeight
  })
  
  const onScroll = (event: Event) => {
    const target = event.target as HTMLElement
    scrollTop.value = target.scrollTop
  }
  
  return {
    visibleItems,
    totalHeight,
    offsetY,
    onScroll,
    visibleRange,
  }
}

/**
 * Оптимизация для real-time обновлений телеметрии
 * Группирует обновления по зонам и метрикам
 */
export function useTelemetryBatch(
  updateFn: (updates: Map<string, Map<string, number>>) => void,
  debounceMs: number = DEBOUNCE_DELAY.NORMAL
) {
  const updates = new Map<string, Map<string, number>>()
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  
  const addUpdate = (zoneId: string, metric: string, value: number) => {
    if (!updates.has(zoneId)) {
      updates.set(zoneId, new Map())
    }
    updates.get(zoneId)!.set(metric, value)
    
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    
    timeoutId = setTimeout(() => {
      updateFn(new Map(updates))
      updates.clear()
      timeoutId = null
    }, debounceMs)
  }
  
  const flush = () => {
    if (updates.size > 0) {
      updateFn(new Map(updates))
      updates.clear()
    }
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }
  
  return {
    addUpdate,
    flush,
  }
}

