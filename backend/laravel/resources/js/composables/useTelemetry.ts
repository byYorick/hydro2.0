/**
 * Composable для работы с телеметрией с кешированием и rate limiting
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import type { ToastHandler } from './useApi'
import { useRateLimitedApi } from './useRateLimitedApi'
import { useErrorHandler } from './useErrorHandler'
import { logger } from '@/utils/logger'
import { extractData } from '@/utils/apiHelpers'
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
      logger.warn('[Telemetry] Cache too large, clearing old entries')
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
    logger.warn('[Telemetry] Failed to save cache to sessionStorage:', err)
    // Если sessionStorage переполнен, очищаем его и пробуем снова
    try {
      sessionStorage.removeItem(STORAGE_KEY)
      const cacheData: Record<string, CacheEntry<ZoneTelemetry | TelemetrySample[]>> = {}
      for (const [key, value] of telemetryCache.entries()) {
        cacheData[key] = value
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(cacheData))
    } catch (e) {
      logger.error('[Telemetry] Failed to recover from storage error:', e)
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
    logger.warn('[Telemetry] Failed to load cache from sessionStorage:', err)
    // Очищаем поврежденные данные
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch (e) {
      logger.error('[Telemetry] Failed to clear corrupted storage:', e)
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
  const { rateLimitedGet } = useRateLimitedApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
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
      const cached = telemetryCache.get(cacheKey)
      if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data as ZoneTelemetry
      }
    }

    loading.value = true
    error.value = null

    try {
      // Используем rate-limited API для предотвращения превышения лимитов
      const response = await rateLimitedGet<{ data?: ZoneTelemetry } | ZoneTelemetry>(
        `/api/zones/${zoneId}/telemetry/last`,
        {},
        {
          retries: 2,
          backoff: 'exponential',
          baseDelay: 1000,
        }
      )
      
      // rateLimitedGet возвращает axios response, нужно обращаться к response.data
      const responseData = (response as any)?.data || response
      const telemetry: ZoneTelemetry = extractData<ZoneTelemetry>(responseData) || {} as ZoneTelemetry
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data: telemetry,
        timestamp: Date.now()
      })
      
      cleanupCache()
      saveCacheToStorage()
      return telemetry
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useTelemetry',
        action: 'fetchLastTelemetry',
        zoneId,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
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
      const cached = telemetryCache.get(cacheKey)
      if (cached && Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data as TelemetrySample[]
      }
    }

    loading.value = true
    error.value = null

    try {
      // Используем rate-limited API для предотвращения превышения лимитов
      const response = await rateLimitedGet<{ data?: Array<{ ts: string; value: number }> }>(
        `/api/zones/${zoneId}/telemetry/history`,
        {
          params: {
            metric,
            ...params
          }
        },
        {
          retries: 2,
          backoff: 'exponential',
          baseDelay: 1000,
        }
      )
      
      // rateLimitedGet возвращает axios response, нужно обращаться к response.data
      const responseData = (response as any)?.data || response
      const data = (responseData as { data?: Array<{ ts: string; value: number }> })?.data || []
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
      const normalizedError = handleError(err, {
        component: 'useTelemetry',
        action: 'fetchHistory',
        zoneId,
        metric,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
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
      const cached = telemetryCache.get(cacheKey)
      if (cached && Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data as TelemetrySample[]
      }
    }

    loading.value = true
    error.value = null

    try {
      // Используем rate-limited API для предотвращения превышения лимитов
      const response = await rateLimitedGet<{ data?: TelemetrySample[] }>(
        '/api/telemetry/aggregates',
        {
          params: {
            zone_id: zoneId,
            metric,
            period
          }
        },
        {
          retries: 2,
          backoff: 'exponential',
          baseDelay: 1000,
        }
      )
      
      // rateLimitedGet возвращает axios response, нужно обращаться к response.data
      const responseData = (response as any)?.data || response
      const data = (responseData as { data?: TelemetrySample[] })?.data || []
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data,
        timestamp: Date.now()
      })
      
      cleanupCache()
      saveCacheToStorage()
      return data
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useTelemetry',
        action: 'fetchAggregates',
        zoneId,
        metric,
        period,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
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

  // Обработчик события reconciliation для обновления телеметрии при переподключении
  function handleReconciliation(event: CustomEvent) {
    const { telemetry } = event.detail || {}
    
    if (!telemetry || !Array.isArray(telemetry)) {
      return
    }

    logger.debug('[useTelemetry] Processing reconciliation telemetry data', {
      count: telemetry.length,
    })

    // Группируем телеметрию по zone_id и обновляем кеш
    const telemetryByZone = new Map<number, ZoneTelemetry>()
    
    for (const item of telemetry) {
      if (!item.zone_id) continue
      
      const zoneId = item.zone_id
      if (!telemetryByZone.has(zoneId)) {
        telemetryByZone.set(zoneId, {} as ZoneTelemetry)
      }
      
      const zoneTelemetry = telemetryByZone.get(zoneId)!
      const key = item.metric_type || 'unknown'
      zoneTelemetry[key] = {
        zone_id: zoneId,
        node_id: item.node_id,
        channel: item.channel,
        metric_type: item.metric_type,
        value: item.value,
        ts: item.ts ? new Date(item.ts) : new Date(),
      } as any
    }

    // Обновляем кеш для каждой зоны
    for (const [zoneId, zoneTelemetry] of telemetryByZone.entries()) {
      const cacheKey = `telemetry_last_${zoneId}`
      telemetryCache.set(cacheKey, {
        data: zoneTelemetry,
        timestamp: Date.now(),
      })
    }

    saveCacheToStorage()
    logger.info('[useTelemetry] Reconciliation completed', {
      zonesUpdated: telemetryByZone.size,
    })
  }

  // Подписываемся на событие reconciliation при монтировании
  onMounted(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('ws:reconciliation:telemetry', handleReconciliation as EventListener)
    }
  })

  onUnmounted(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('ws:reconciliation:telemetry', handleReconciliation as EventListener)
    }
  })

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
    logger.warn('[Telemetry] Failed to clear sessionStorage:', err)
  }
}
