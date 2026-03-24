import { ref, type Ref } from 'vue'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'

export type AutomationScopeType = 'system' | 'zone' | 'grow_cycle'

export interface AutomationDocument<TPayload = Record<string, unknown>> {
  namespace: string
  scope_type: AutomationScopeType
  scope_id: number
  schema_version: number
  payload: TPayload
  status: string
  updated_at: string | null
  updated_by: number | null
}

export interface AutomationViolation {
  namespace: string
  path: string
  code: string
  severity: string
  blocking: boolean
  message: string
}

export interface AutomationBundle {
  scope_type: AutomationScopeType
  scope_id: number
  bundle_revision: string
  status: string
  config: Record<string, unknown>
  violations: AutomationViolation[]
  compiled_at: string | null
}

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

export function useAutomationConfig(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  async function getDocument<TPayload = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
  ): Promise<AutomationDocument<TPayload>> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: AutomationDocument<TPayload> }>(
        `/automation-configs/${scopeType}/${scopeId}/${namespace}`
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateDocument<TPayload = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
    payload: TPayload,
  ): Promise<AutomationDocument<TPayload>> {
    loading.value = true
    error.value = null

    try {
      const response = await api.put<{ status: string; data: AutomationDocument<TPayload> }>(
        `/automation-configs/${scopeType}/${scopeId}/${namespace}`,
        { payload }
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getBundle(scopeType: AutomationScopeType, scopeId: number): Promise<AutomationBundle> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: AutomationBundle }>(
        `/automation-bundles/${scopeType}/${scopeId}`
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function validateBundle(scopeType: AutomationScopeType, scopeId: number): Promise<AutomationBundle> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ status: string; data: AutomationBundle }>(
        `/automation-bundles/${scopeType}/${scopeId}/validate`
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function listPresets(namespace: string): Promise<AutomationPreset[]> {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{ status: string; data: AutomationPreset[] }>(
        `/automation-presets/${namespace}`
      )
      return Array.isArray(response.data.data) ? response.data.data : []
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function createPreset(namespace: string, payload: {
    name: string
    description?: string | null
    payload: Record<string, unknown>
  }): Promise<AutomationPreset> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ status: string; data: AutomationPreset }>(
        `/automation-presets/${namespace}`,
        payload
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updatePreset(presetId: number, payload: {
    name?: string
    description?: string | null
    payload?: Record<string, unknown>
  }): Promise<AutomationPreset> {
    loading.value = true
    error.value = null

    try {
      const response = await api.put<{ status: string; data: AutomationPreset }>(
        `/automation-presets/${presetId}`,
        payload
      )
      return response.data.data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deletePreset(presetId: number): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await api.delete(`/automation-presets/${presetId}`)
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function duplicatePreset(presetId: number): Promise<AutomationPreset> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ status: string; data: AutomationPreset }>(
        `/automation-presets/${presetId}/duplicate`
      )
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
    getDocument,
    updateDocument,
    getBundle,
    validateBundle,
    listPresets,
    createPreset,
    updatePreset,
    deletePreset,
    duplicatePreset,
  }
}
