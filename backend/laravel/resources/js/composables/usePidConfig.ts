/**
 * Composable для работы с PID конфигами
 */
import { ref, type Ref } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'
import type { PidConfig, PidConfigWithMeta, PidLog } from '@/types/PidConfig'

/**
 * Composable для работы с PID конфигами
 */
export function usePidConfig(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  /**
   * Получить PID конфиг для зоны и типа
   */
  async function getPidConfig(zoneId: number, type: 'ph' | 'ec'): Promise<PidConfigWithMeta> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: PidConfigWithMeta }>(
        `/zones/${zoneId}/pid-configs/${type}`
      )

      if (response.data.status === 'ok') {
        return response.data.data
      } else {
        throw new Error('Failed to fetch PID config')
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить все PID конфиги для зоны
   */
  async function getAllPidConfigs(zoneId: number): Promise<Record<'ph' | 'ec', PidConfigWithMeta>> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: Record<'ph' | 'ec', PidConfigWithMeta> }>(
        `/zones/${zoneId}/pid-configs`
      )

      if (response.data.status === 'ok') {
        return response.data.data
      } else {
        throw new Error('Failed to fetch PID configs')
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Обновить PID конфиг для зоны и типа
   */
  async function updatePidConfig(
    zoneId: number,
    type: 'ph' | 'ec',
    config: PidConfig
  ): Promise<PidConfigWithMeta> {
    loading.value = true
    error.value = null

    try {
      const response = await api.put<{ status: string; data: PidConfigWithMeta }>(
        `/zones/${zoneId}/pid-configs/${type}`,
        { config }
      )

      if (response.data.status === 'ok') {
        return response.data.data
      } else {
        throw new Error(response.data.status === 'error' ? 'Failed to update PID config' : 'Unknown error')
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить логи PID для зоны
   */
  async function getPidLogs(
    zoneId: number,
    options?: {
      type?: 'ph' | 'ec'
      limit?: number
      offset?: number
    }
  ): Promise<{ logs: PidLog[]; total: number; limit: number; offset: number }> {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      if (options?.type) {
        params.append('type', options.type)
      }
      if (options?.limit) {
        params.append('limit', options.limit.toString())
      }
      if (options?.offset) {
        params.append('offset', options.offset.toString())
      }

      const response = await api.get<{
        status: string
        data: PidLog[]
        meta: { total: number; limit: number; offset: number }
      }>(`/zones/${zoneId}/pid-logs?${params.toString()}`)

      if (response.data.status === 'ok') {
        return {
          logs: response.data.data,
          total: response.data.meta.total,
          limit: response.data.meta.limit,
          offset: response.data.meta.offset,
        }
      } else {
        throw new Error('Failed to fetch PID logs')
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    getPidConfig,
    getAllPidConfigs,
    updatePidConfig,
    getPidLogs,
  }
}

