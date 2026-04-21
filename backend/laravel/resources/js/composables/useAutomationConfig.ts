import { ref, type Ref } from 'vue'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import { useErrorHandler } from './useErrorHandler'

export type AutomationScopeType = 'system' | 'greenhouse' | 'zone' | 'grow_cycle'

export interface AutomationDocument<
  TPayload = Record<string, unknown>,
  TMeta = Record<string, unknown>,
> {
  id?: number | null
  namespace: string
  scope_type: AutomationScopeType
  scope_id: number
  schema_version: number
  payload: TPayload
  meta?: TMeta
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
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  async function getDocument<TPayload = Record<string, unknown>, TMeta = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
  ): Promise<AutomationDocument<TPayload, TMeta>> {
    loading.value = true
    error.value = null

    try {
      return await api.automationConfigs.get<AutomationDocument<TPayload, TMeta>>(
        scopeType,
        scopeId,
        namespace,
      )
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updateDocument<
    TRequestPayload = Record<string, unknown>,
    TResponsePayload = TRequestPayload,
    TMeta = Record<string, unknown>,
  >(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
    payload: TRequestPayload,
  ): Promise<AutomationDocument<TResponsePayload, TMeta>> {
    loading.value = true
    error.value = null

    try {
      return await api.automationConfigs.update<AutomationDocument<TResponsePayload, TMeta>>(
        scopeType,
        scopeId,
        namespace,
        payload as Record<string, unknown>,
      )
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
      return await api.automationBundles.get(scopeType, scopeId) as AutomationBundle
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
      return await api.automationBundles.validate(scopeType, scopeId) as AutomationBundle
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
      const result = await api.automationPresets.list(namespace)
      return Array.isArray(result) ? result : []
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
      return await api.automationPresets.create(namespace, payload)
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
      return await api.automationPresets.update(presetId, payload)
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
      await api.automationPresets.delete(presetId)
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
      return await api.automationPresets.duplicate(presetId)
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getHistory<TVersion = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
  ): Promise<TVersion[]> {
    loading.value = true
    error.value = null

    try {
      const result = await api.automationConfigs.getHistory<TVersion>(scopeType, scopeId, namespace)
      return Array.isArray(result) ? result : []
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getRevision<TPayload = Record<string, unknown>, TMeta = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
    version: number,
  ): Promise<AutomationDocument<TPayload, TMeta>> {
    loading.value = true
    error.value = null

    try {
      return await api.automationConfigs.getRevision<AutomationDocument<TPayload, TMeta>>(
        scopeType,
        scopeId,
        namespace,
        version,
      )
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function restoreRevision<TPayload = Record<string, unknown>, TMeta = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
    version: number,
  ): Promise<AutomationDocument<TPayload, TMeta>> {
    loading.value = true
    error.value = null

    try {
      return await api.automationConfigs.restoreRevision<AutomationDocument<TPayload, TMeta>>(
        scopeType,
        scopeId,
        namespace,
        version,
      )
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function resetDocument<TPayload = Record<string, unknown>, TMeta = Record<string, unknown>>(
    scopeType: AutomationScopeType,
    scopeId: number,
    namespace: string,
  ): Promise<AutomationDocument<TPayload, TMeta>> {
    loading.value = true
    error.value = null

    try {
      return await api.automationConfigs.reset<AutomationDocument<TPayload, TMeta>>(
        scopeType,
        scopeId,
        namespace,
      )
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
    getHistory,
    getRevision,
    restoreRevision,
    resetDocument,
    getBundle,
    validateBundle,
    listPresets,
    createPreset,
    updatePreset,
    deletePreset,
    duplicatePreset,
  }
}
