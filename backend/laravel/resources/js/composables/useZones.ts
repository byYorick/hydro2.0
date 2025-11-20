/**
 * Composable для управления зонами с кешированием и Inertia partial reloads
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'
import type { Zone } from '@/types'

// Кеш в памяти (TTL 10-30 секунд)
interface CacheEntry {
  data: Zone | Zone[]
  timestamp: number
}

const zonesCache = new Map<string, CacheEntry>()
const CACHE_TTL = 10 * 1000 // 10 секунд

/**
 * Очистка устаревших записей из кеша
 */
function cleanupCache(): void {
  const now = Date.now()
  for (const [key, value] of zonesCache.entries()) {
    if (now - value.timestamp > CACHE_TTL) {
      zonesCache.delete(key)
    }
  }
}

/**
 * Composable для работы с зонами
 */
export function useZones(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  /**
   * Получить список всех зон
   */
  async function fetchZones(forceRefresh: boolean = false): Promise<Zone[]> {
    const cacheKey = 'zones_list'
    
    // Проверяем кеш
    if (!forceRefresh && zonesCache.has(cacheKey)) {
      const cached = zonesCache.get(cacheKey)!
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data as Zone[]
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ data?: Zone[] } | Zone[]>('/api/zones')
      const zones = ((response.data as { data?: Zone[] })?.data || 
                    (response.data as Zone[]) || 
                    []) as Zone[]
      
      // Сохраняем в кеш
      zonesCache.set(cacheKey, {
        data: zones,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return zones
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useZones',
        action: 'fetchZones',
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить детальную информацию о зоне
   */
  async function fetchZone(zoneId: number, forceRefresh: boolean = false): Promise<Zone> {
    const cacheKey = `zone_${zoneId}`
    
    // Проверяем кеш
    if (!forceRefresh && zonesCache.has(cacheKey)) {
      const cached = zonesCache.get(cacheKey)!
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data as Zone
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ data?: Zone } | Zone>(`/api/zones/${zoneId}`)
      const zone = ((response.data as { data?: Zone })?.data || 
                   (response.data as Zone)) as Zone
      
      // Сохраняем в кеш
      zonesCache.set(cacheKey, {
        data: zone,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return zone
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useZones',
        action: 'fetchZone',
        zoneId,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
    } finally {
      loading.value = false
    }
  }

  /**
   * Обновить зону через Inertia partial reload
   */
  function reloadZone(zoneId: number, only: string[] = ['zone']): void {
    router.reload({ only })
  }

  /**
   * Обновить список зон через Inertia partial reload
   */
  function reloadZones(only: string[] = ['zones']): void {
    router.reload({ only })
  }

  /**
   * Очистить кеш для конкретной зоны или всех зон
   */
  function clearCache(zoneId: number | null = null): void {
    if (zoneId) {
      zonesCache.delete(`zone_${zoneId}`)
    } else {
      zonesCache.clear()
    }
  }

  return {
    loading: computed(() => loading.value) as ComputedRef<boolean>,
    error: computed(() => error.value) as ComputedRef<Error | null>,
    fetchZones,
    fetchZone,
    reloadZone,
    reloadZones,
    clearCache,
  }
}

/**
 * Очистить весь кеш зон (для тестирования)
 */
export function clearZonesCache(): void {
  zonesCache.clear()
}

