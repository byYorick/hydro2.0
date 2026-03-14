import { useApi } from '@/composables/useApi'
import type { SettingsNamespacePayload } from '@/types/SystemSettings'

export function useSystemSettings() {
  const { api } = useApi()

  async function getAll(): Promise<Record<string, SettingsNamespacePayload>> {
    const response = await api.get('/api/system/automation-settings')
    return response.data.data as Record<string, SettingsNamespacePayload>
  }

  async function getNamespace(namespace: string): Promise<SettingsNamespacePayload> {
    const response = await api.get(`/api/system/automation-settings/${namespace}`)
    return response.data.data as SettingsNamespacePayload
  }

  async function updateNamespace(namespace: string, config: Record<string, unknown>): Promise<SettingsNamespacePayload> {
    const response = await api.put(`/api/system/automation-settings/${namespace}`, { config })
    return response.data.data as SettingsNamespacePayload
  }

  async function resetNamespace(namespace: string): Promise<SettingsNamespacePayload> {
    const response = await api.post(`/api/system/automation-settings/${namespace}/reset`)
    return response.data.data as SettingsNamespacePayload
  }

  return {
    getAll,
    getNamespace,
    updateNamespace,
    resetNamespace,
  }
}
