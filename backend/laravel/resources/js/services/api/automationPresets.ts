/**
 * Automation presets API client.
 */
import { apiGet, apiPost, apiPut, apiDelete } from './_client'

export interface AutomationPreset {
  id: number
  namespace: string
  scope: 'system' | 'custom'
  is_locked: boolean
  name: string
  slug: string
  description: string | null
  schema_version: number
  payload: Record<string, unknown>
  updated_by: number | null
  updated_at: string | null
}

export interface AutomationPresetCreatePayload {
  name: string
  description?: string | null
  payload: Record<string, unknown>
}

export interface AutomationPresetUpdatePayload {
  name?: string
  description?: string | null
  payload?: Record<string, unknown>
}

export const automationPresetsApi = {
  list(namespace: string): Promise<AutomationPreset[]> {
    return apiGet<AutomationPreset[]>(`/automation-presets/${namespace}`)
  },

  create(namespace: string, payload: AutomationPresetCreatePayload): Promise<AutomationPreset> {
    return apiPost<AutomationPreset>(`/automation-presets/${namespace}`, payload)
  },

  update(presetId: number, payload: AutomationPresetUpdatePayload): Promise<AutomationPreset> {
    return apiPut<AutomationPreset>(`/automation-presets/${presetId}`, payload)
  },

  delete(presetId: number): Promise<void> {
    return apiDelete<void>(`/automation-presets/${presetId}`)
  },

  duplicate(presetId: number): Promise<AutomationPreset> {
    return apiPost<AutomationPreset>(`/automation-presets/${presetId}/duplicate`)
  },
}
