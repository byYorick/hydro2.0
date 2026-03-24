import { ref, type Ref } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'
import type {
  CorrectionPreset,
  ZoneCorrectionConfigHistoryItem,
  ZoneCorrectionConfigPayload,
} from '@/types/CorrectionConfig'

const CORRECTION_PRESET_NAMESPACE = 'zone.correction'

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
        `/automation-configs/zone/${zoneId}/zone.correction`
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
        `/automation-configs/zone/${zoneId}/zone.correction`,
        { payload }
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
        `/automation-configs/zone/${zoneId}/zone.correction/history`
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
      const createResponse = await api.post<{ status: string; data: { id: number } }>(
        `/automation-presets/${CORRECTION_PRESET_NAMESPACE}`,
        {
          name: payload.name,
          description: payload.description,
          payload: payload.config,
        }
      )
      const listResponse = await api.get<{ status: string; data: Array<CorrectionPreset & { payload?: Record<string, unknown> }> }>(
        `/automation-presets/${CORRECTION_PRESET_NAMESPACE}`
      )

      return {
        data: Array.isArray(listResponse.data.data)
          ? listResponse.data.data.map(normalizePreset)
          : [],
        selected: createResponse.data.data.id,
      }
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
      await api.delete(`/automation-presets/${presetId}`)
      const response = await api.get<{ status: string; data: Array<CorrectionPreset & { payload?: Record<string, unknown> }> }>(
        `/automation-presets/${CORRECTION_PRESET_NAMESPACE}`
      )

      return Array.isArray(response.data.data) ? response.data.data.map(normalizePreset) : []
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

function normalizePreset(preset: CorrectionPreset & { payload?: Record<string, unknown> }): CorrectionPreset {
  return {
    ...preset,
    config: preset.config ?? preset.payload ?? {},
  }
}
