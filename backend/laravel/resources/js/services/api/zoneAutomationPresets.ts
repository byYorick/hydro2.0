import { apiGet, apiPost, apiPut, apiDelete } from './_client'
import type {
  ZoneAutomationPreset,
  ZoneAutomationPresetCreatePayload,
  ZoneAutomationPresetUpdatePayload,
  ZoneAutomationPresetFilters,
} from '@/types/ZoneAutomationPreset'

function buildQuery(filters?: ZoneAutomationPresetFilters): string {
  if (!filters) return ''
  const params = new URLSearchParams()
  if (filters.tanks_count !== undefined) params.set('tanks_count', String(filters.tanks_count))
  if (filters.irrigation_system_type) params.set('irrigation_system_type', filters.irrigation_system_type)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export const zoneAutomationPresetsApi = {
  list(filters?: ZoneAutomationPresetFilters): Promise<ZoneAutomationPreset[]> {
    return apiGet<ZoneAutomationPreset[]>(`/zone-automation-presets${buildQuery(filters)}`)
  },

  getById(id: number): Promise<ZoneAutomationPreset> {
    return apiGet<ZoneAutomationPreset>(`/zone-automation-presets/${id}`)
  },

  create(payload: ZoneAutomationPresetCreatePayload): Promise<ZoneAutomationPreset> {
    return apiPost<ZoneAutomationPreset>('/zone-automation-presets', payload)
  },

  update(id: number, payload: ZoneAutomationPresetUpdatePayload): Promise<ZoneAutomationPreset> {
    return apiPut<ZoneAutomationPreset>(`/zone-automation-presets/${id}`, payload)
  },

  delete(id: number): Promise<void> {
    return apiDelete<void>(`/zone-automation-presets/${id}`)
  },

  duplicate(id: number): Promise<ZoneAutomationPreset> {
    return apiPost<ZoneAutomationPreset>(`/zone-automation-presets/${id}/duplicate`)
  },
}
