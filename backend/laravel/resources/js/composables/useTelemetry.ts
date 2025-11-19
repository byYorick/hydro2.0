/**
 * Composable для работы с телеметрией с кешированием
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import type { ZoneTelemetry, TelemetrySample, TelemetryMetric } from '@/types'

// Кеш в памяти (TTL 30-60 секунд для телеметрии)
interface CacheEntry<T> {
  data: T
  timestamp: number
}

const telemetryCache = new Map<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>>()
const CACHE_TTL = 30 * 1000 // 30 секунд
const HISTORY_CACHE_TTL = 60 * 1000 // 60 секунд для истории
const STORAGE_KEY = 'hydro_telemetry_cache'
const MAX_STORAGE_SIZE = 5 * 1024 * 1024 // 5MB максимум для sessionStorage

/**
 * Сохранить кеш в sessionStorage
 */
function saveCacheToStorage(): void {
  try {
    const cacheData: Record<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>> = {}
    for (const [key, value] of telemetryCache.entries()) {
      cacheData[key] = value
    }
    const json = JSON.stringify(cacheData)
    
    // Проверяем размер перед сохранением
    if (json.length > MAX_STORAGE_SIZE) {
      console.warn('[Telemetry] Cache too large, clearing old entries')
      // Удаляем самые старые записи
      const sorted = Array.from(telemetryCache.entries())
        .sort((a, b) => a[1].timestamp - b[1].timestamp)
      
      // Удаляем 50% самых старых записей
      for (let i = 0; i < Math.floor(sorted.length / 2); i++) {
        telemetryCache.delete(sorted[i][0])
      }
      
      // Повторно сохраняем
      const newCacheData: Record<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>> = {}
      for (const [key, value] of telemetryCache.entries()) {
        newCacheData[key] = value
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(newCacheData))
    } else {
      sessionStorage.setItem(STORAGE_KEY, json)
    }
  } catch (err) {
    console.warn('[Telemetry] Failed to save cache to sessionStorage:', err)
    // Если sessionStorage переполнен, очищаем его и пробуем снова
    try {
      sessionStorage.removeItem(STORAGE_KEY)
      const cacheData: Record<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>> = {}
      for (const [key, value] of telemetryCache.entries()) {
        cacheData[key] = value
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(cacheData))
    } catch (e) {
      console.error('[Telemetry] Failed to recover from storage error:', e)
    }
  }
}

/**
 * Загрузить кеш из sessionStorage
 */
function loadCacheFromStorage(): void {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY)
    if (!stored) return
    
    const cacheData = JSON.parse(stored) as Record<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>>
    const now = Date.now()
    
    // Загружаем только валидные записи (не устаревшие)
    for (const [key, entry] of Object.entries(cacheData)) {
      const ttl = key.includes('history') || key.includes('aggregates') ? HISTORY_CACHE_TTL : CACHE_TTL
      if (now - entry.timestamp < ttl) {
        telemetryCache.set(key, entry)
      }
    }
  } catch (err) {
    console.warn('[Telemetry] Failed to load cache from sessionStorage:', err)
    // Очищаем поврежденные данные
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch (e) {
      console.error('[Telemetry] Failed to clear corrupted storage:', e)
    }
  }
}

// Загружаем кеш при инициализации модуля
loadCacheFromStorage()

/**
 * Очистка устаревших записей из кеша
 */
function cleanupCache(): void {
  const now = Date.now()
  let hasChanges = false
  for (const [key, value] of telemetryCache.entries()) {
    const ttl = key.includes('history') || key.includes('aggregates') ? HISTORY_CACHE_TTL : CACHE_TTL
    if (now - value.timestamp > ttl) {
      telemetryCache.delete(key)
      hasChanges = true
    }
  }
  // Сохраняем изменения в storage только если были удаления
  if (hasChanges) {
    saveCacheToStorage()
  }
}

/**
 * Composable для работы с телеметрией
 */
export function useTelemetry(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  /**
   * Получить последнюю телеметрию для зоны
   */
  async function fetchLastTelemetry(
    zoneId: number,
    forceRefresh: boolean = false
  ): Promise<ZoneTelemetry> {
    const cacheKey = `telemetry_last_${zoneId}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)!
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data as ZoneTelemetry
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ data?: ZoneTelemetry } | ZoneTelemetry>(
        `/api/zones/${zoneId}/telemetry/last`
      )
      const telemetry = (response.data as { data?: ZoneTelemetry })?.data || 
                       (response.data as ZoneTelemetry) || 
                       {} as ZoneTelemetry
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data: telemetry,
        timestamp: Date.now()
      })
      
      cleanupCache()
      saveCacheToStorage()
      return telemetry
    } catch (err) {
      error.value = err as Error
      if (showToast) {
        showToast('Ошибка при загрузке телеметрии', 'error', 5000)
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить историю телеметрии для зоны
   */
  async function fetchHistory(
    zoneId: number,
    metric: TelemetryMetric,
    params: { from?: string; to?: string } = {},
    forceRefresh: boolean = false
  ): Promise<TelemetrySample[]> {
    const cacheKey = `telemetry_history_${zoneId}_${metric}_${JSON.stringify(params)}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)!
      if (Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data as TelemetrySample[]
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ data?: Array<{ ts: string; value: number }> }>(
        `/api/zones/${zoneId}/telemetry/history`,
        {
          params: {
            metric,
            ...params
          }
        }
      )
      
      const data = (response.data as { data?: Array<{ ts: string; value: number }> })?.data || []
      const history: TelemetrySample[] = data.map(item => ({
        ts: new Date(item.ts).getTime(),
        value: item.value,
      }))
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data: history,
        timestamp: Date.now()
      })
      
      cleanupCache()
      saveCacheToStorage()
      return history
    } catch (err) {
      error.value = err as Error
      if (showToast) {
        showToast(`Ошибка при загрузке истории ${metric}`, 'error', 5000)
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить агрегированные данные телеметрии (для мини-графиков)
   */
  async function fetchAggregates(
    zoneId: number,
    metric: string,
    period: string = '24h',
    forceRefresh: boolean = false
  ): Promise<TelemetrySample[]> {
    const cacheKey = `telemetry_aggregates_${zoneId}_${metric}_${period}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)!
      if (Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data as TelemetrySample[]
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ data?: TelemetrySample[] }>(
        '/api/telemetry/aggregates',
        {
          params: {
            zone_id: zoneId,
            metric,
            period
          }
        }
      )
      
      const data = (response.data as { data?: TelemetrySample[] })?.data || []
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data,
        timestamp: Date.now()
      })
      
      cleanupCache()
      saveCacheToStorage()
      return data
    } catch (err) {
      error.value = err as Error
      if (showToast) {
        showToast(`Ошибка при загрузке агрегированных данных ${metric}`, 'error', 5000)
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Очистить кеш для конкретной зоны или всей телеметрии
   */
  function clearCache(zoneId: number | null = null): void {
    if (zoneId) {
      for (const key of telemetryCache.keys()) {
        if (key.includes(`_${zoneId}_`)) {
          telemetryCache.delete(key)
        }
      }
    } else {
      telemetryCache.clear()
    }
    saveCacheToStorage()
  }

  return {
    loading: computed(() => loading.value) as ComputedRef<boolean>,
    error: computed(() => error.value) as ComputedRef<Error | null>,
    fetchLastTelemetry,
    fetchHistory,
    fetchAggregates,
    clearCache,
  }
}

/**
 * Очистить весь кеш телеметрии (для тестирования)
 */
export function clearTelemetryCache(): void {
  telemetryCache.clear()
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch (err) {
    console.warn('[Telemetry] Failed to clear sessionStorage:', err)
  }
}

