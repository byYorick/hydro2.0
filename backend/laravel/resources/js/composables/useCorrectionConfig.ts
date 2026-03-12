import { ref, type Ref } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'
import type {
  CorrectionPreset,
  ZoneCorrectionConfigHistoryItem,
  ZoneCorrectionConfigPayload,
} from '@/types/CorrectionConfig'

export function useCorrectionConfig(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  async function getZoneCorrectionConfig(zoneId: number): Promise<ZoneCorrectionConfigPayload> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: ZoneCorrectionConfigPayload }>(
        `/zones/${zoneId}/correction-config`
      )
      if (response.data.status !== 'ok') {
        throw new Error('Failed to fetch zone correction config')
      }
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateZoneCorrectionConfig(
    zoneId: number,
    payload: {
      preset_id: number | null
      base_config: Record<string, unknown>
      phase_overrides: Record<string, Record<string, unknown>>
    }
  ): Promise<ZoneCorrectionConfigPayload> {
    loading.value = true
    error.value = null

    try {
      const response = await api.put<{ status: string; data: ZoneCorrectionConfigPayload }>(
        `/zones/${zoneId}/correction-config`,
        payload
      )
      if (response.data.status !== 'ok') {
        throw new Error('Failed to update zone correction config')
      }
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getZoneCorrectionConfigHistory(zoneId: number): Promise<ZoneCorrectionConfigHistoryItem[]> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: ZoneCorrectionConfigHistoryItem[] }>(
        `/zones/${zoneId}/correction-config/history`
      )
      if (response.data.status !== 'ok') {
        throw new Error('Failed to fetch correction config history')
      }
      return Array.isArray(response.data.data) ? response.data.data : []
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function createCorrectionPreset(payload: {
    name: string
    description?: string | null
    config: Record<string, unknown>
  }): Promise<{ data: CorrectionPreset[]; selected: number }> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ status: string; data: CorrectionPreset[]; selected: number }>(
        '/correction-config-presets',
        payload
      )
      if (response.data.status !== 'ok') {
        throw new Error('Failed to create correction preset')
      }
      return { data: response.data.data, selected: response.data.selected }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteCorrectionPreset(presetId: number): Promise<CorrectionPreset[]> {
    loading.value = true
    error.value = null

    try {
      const response = await api.delete<{ status: string; data: CorrectionPreset[] }>(
        `/correction-config-presets/${presetId}`
      )
      if (response.data.status !== 'ok') {
        throw new Error('Failed to delete correction preset')
      }
      return response.data.data
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
    getZoneCorrectionConfig,
    updateZoneCorrectionConfig,
    getZoneCorrectionConfigHistory,
    createCorrectionPreset,
    deleteCorrectionPreset,
  }
}
