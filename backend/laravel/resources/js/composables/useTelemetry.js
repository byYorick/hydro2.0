/**
 * Composable для работы с телеметрией с кешированием
 */
import { ref, computed } from 'vue'
import { useApi } from './useApi'

// Кеш в памяти (TTL 30-60 секунд для телеметрии)
const telemetryCache = new Map()
const CACHE_TTL = 30 * 1000 // 30 секунд
const HISTORY_CACHE_TTL = 60 * 1000 // 60 секунд для истории

/**
 * Очистка устаревших записей из кеша
 */
function cleanupCache() {
  const now = Date.now()
  for (const [key, value] of telemetryCache.entries()) {
    const ttl = key.includes('history') ? HISTORY_CACHE_TTL : CACHE_TTL
    if (now - value.timestamp > ttl) {
      telemetryCache.delete(key)
    }
  }
}

/**
 * Composable для работы с телеметрией
 * @param {Function} showToast - Функция для показа Toast уведомлений
 * @returns {Object} Методы для работы с телеметрией
 */
export function useTelemetry(showToast = null) {
  const { api } = useApi(showToast)
  const loading = ref(false)
  const error = ref(null)

  /**
   * Получить последнюю телеметрию для зоны
   * @param {number} zoneId - ID зоны
   * @param {boolean} forceRefresh - Принудительно обновить данные
   * @returns {Promise<Object>} Последняя телеметрия
   */
  async function fetchLastTelemetry(zoneId, forceRefresh = false) {
    const cacheKey = `telemetry_last_${zoneId}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)
      if (Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get(`/api/zones/${zoneId}/telemetry/last`)
      const telemetry = response.data?.data || response.data || {}
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data: telemetry,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return telemetry
    } catch (err) {
      error.value = err
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
   * @param {number} zoneId - ID зоны
   * @param {string} metric - Метрика (PH, EC, TEMP, HUMIDITY)
   * @param {Object} params - Параметры запроса (from, to)
   * @param {boolean} forceRefresh - Принудительно обновить данные
   * @returns {Promise<Array>} История телеметрии
   */
  async function fetchHistory(zoneId, metric, params = {}, forceRefresh = false) {
    const cacheKey = `telemetry_history_${zoneId}_${metric}_${JSON.stringify(params)}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)
      if (Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get(`/api/zones/${zoneId}/telemetry/history`, {
        params: {
          metric,
          ...params
        }
      })
      
      const data = response.data?.data || []
      const history = data.map(item => ({
        ts: new Date(item.ts).getTime(),
        value: item.value,
      }))
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data: history,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return history
    } catch (err) {
      error.value = err
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
   * @param {number} zoneId - ID зоны
   * @param {string} metric - Метрика (ph, ec, temp, humidity)
   * @param {string} period - Период (24h, 7d, 30d)
   * @param {boolean} forceRefresh - Принудительно обновить данные
   * @returns {Promise<Array>} Агрегированные данные
   */
  async function fetchAggregates(zoneId, metric, period = '24h', forceRefresh = false) {
    const cacheKey = `telemetry_aggregates_${zoneId}_${metric}_${period}`
    
    // Проверяем кеш
    if (!forceRefresh && telemetryCache.has(cacheKey)) {
      const cached = telemetryCache.get(cacheKey)
      if (Date.now() - cached.timestamp < HISTORY_CACHE_TTL) {
        return cached.data
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get('/api/telemetry/aggregates', {
        params: {
          zone_id: zoneId,
          metric,
          period
        }
      })
      
      const data = response.data?.data || []
      
      // Сохраняем в кеш
      telemetryCache.set(cacheKey, {
        data,
        timestamp: Date.now()
      })
      
      cleanupCache()
      return data
    } catch (err) {
      error.value = err
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
   * @param {number|null} zoneId - ID зоны (если null, очистить весь кеш)
   */
  function clearCache(zoneId = null) {
    if (zoneId) {
      for (const key of telemetryCache.keys()) {
        if (key.includes(`_${zoneId}_`)) {
          telemetryCache.delete(key)
        }
      }
    } else {
      telemetryCache.clear()
    }
  }

  return {
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    fetchLastTelemetry,
    fetchHistory,
    fetchAggregates,
    clearCache,
  }
}

/**
 * Очистить весь кеш телеметрии (для тестирования)
 */
export function clearTelemetryCache() {
  telemetryCache.clear()
}

