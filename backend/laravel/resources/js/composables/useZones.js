/**
 * Composable для управления зонами с кешированием и Inertia partial reloads
 */
import { ref, computed } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi } from './useApi'

// Кеш в памяти (TTL 10-30 секунд)
const zonesCache = new Map()
const CACHE_TTL = 10 * 1000 // 10 секунд

/**
 * Очистка устаревших записей из кеша
 */
function cleanupCache() {
  const now = Date.now()
  for (const [key, value] of zonesCache.entries()) {
    if (now - value.timestamp > CACHE_TTL) {
      zonesCache.delete(key)
    }
  }
}

/**
 * Composable для работы с зонами
 * @param {Function} showToast - Функция для показа Toast уведомлений
 * @returns {Object} Методы для работы с зонами
 */
export function useZones(showToast = null) {
  const { api } = useApi(showToast)
  const loading = ref(false)
  const error = ref(null)

  /**
   * Получить список всех зон
   * @param {boolean} forceRefresh - Принудительно обновить данные (игнорировать кеш)
   * @returns {Promise<Array>} Список зон
   */
  async function fetchZones(forceRefresh = false) {
    const cacheKey = 'zones_list'
    
    // Проверяем кеш
    if (!forceRefresh && zonesCache.has(cacheKey)) {
      const cached = zonesCache.get(cacheKey)
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get('/api/zones')
      const zones = response.data?.data || response.data || []
      
      // Сохраняем в кеш
      zonesCache.set(cacheKey, {
        data: zones,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return zones
    } catch (err) {
      error.value = err
      if (showToast) {
        showToast('Ошибка при загрузке зон', 'error', 5000)
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить детальную информацию о зоне
   * @param {number} zoneId - ID зоны
   * @param {boolean} forceRefresh - Принудительно обновить данные
   * @returns {Promise<Object>} Данные зоны
   */
  async function fetchZone(zoneId, forceRefresh = false) {
    const cacheKey = `zone_${zoneId}`
    
    // Проверяем кеш
    if (!forceRefresh && zonesCache.has(cacheKey)) {
      const cached = zonesCache.get(cacheKey)
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get(`/api/zones/${zoneId}`)
      const zone = response.data?.data || response.data
      
      // Сохраняем в кеш
      zonesCache.set(cacheKey, {
        data: zone,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return zone
    } catch (err) {
      error.value = err
      if (showToast) {
        showToast('Ошибка при загрузке зоны', 'error', 5000)
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Обновить зону через Inertia partial reload
   * @param {number} zoneId - ID зоны
   * @param {Array<string>} only - Список props для обновления (по умолчанию ['zone'])
   */
  function reloadZone(zoneId, only = ['zone']) {
    router.reload({ only })
  }

  /**
   * Обновить список зон через Inertia partial reload
   * @param {Array<string>} only - Список props для обновления (по умолчанию ['zones'])
   */
  function reloadZones(only = ['zones']) {
    router.reload({ only })
  }

  /**
   * Очистить кеш для конкретной зоны или всех зон
   * @param {number|null} zoneId - ID зоны (если null, очистить весь кеш)
   */
  function clearCache(zoneId = null) {
    if (zoneId) {
      zonesCache.delete(`zone_${zoneId}`)
    } else {
      zonesCache.clear()
    }
  }

  return {
    loading: computed(() => loading.value),
    error: computed(() => error.value),
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
export function clearZonesCache() {
  zonesCache.clear()
}

