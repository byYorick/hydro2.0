import { useApi } from '@/composables/useApi'
import type { SettingsNamespacePayload } from '@/types/SystemSettings'

const SYSTEM_NAMESPACE_MAP: Record<string, string> = {
  automation_defaults: 'system.automation_defaults',
  automation_command_templates: 'system.command_templates',
  process_calibration_defaults: 'system.process_calibration_defaults',
  pid_defaults_ph: 'system.pid_defaults.ph',
  pid_defaults_ec: 'system.pid_defaults.ec',
  pump_calibration: 'system.pump_calibration_policy',
  sensor_calibration: 'system.sensor_calibration_policy',
}

export function useSystemSettings() {
  const { api } = useApi()

  async function getAll(): Promise<Record<string, SettingsNamespacePayload>> {
    const entries = await Promise.all(
      Object.entries(SYSTEM_NAMESPACE_MAP).map(async ([legacyNamespace, authorityNamespace]) => {
        const response = await api.get(`/api/automation-configs/system/0/${authorityNamespace}`)
        return [legacyNamespace, {
          namespace: legacyNamespace,
          config: response.data.data.payload,
          meta: {
            defaults: response.data.data.payload,
            field_catalog: [],
          },
        }] as const
      }),
    )

    return Object.fromEntries(entries) as Record<string, SettingsNamespacePayload>
  }

  async function getNamespace(namespace: string): Promise<SettingsNamespacePayload> {
    const authorityNamespace = SYSTEM_NAMESPACE_MAP[namespace] ?? namespace
    const response = await api.get(`/api/automation-configs/system/0/${authorityNamespace}`)

    return {
      namespace,
      config: response.data.data.payload as Record<string, unknown>,
      meta: {
        defaults: response.data.data.payload as Record<string, unknown>,
        field_catalog: [],
      },
    } as SettingsNamespacePayload
  }

  async function updateNamespace(namespace: string, config: Record<string, unknown>): Promise<SettingsNamespacePayload> {
    const authorityNamespace = SYSTEM_NAMESPACE_MAP[namespace] ?? namespace
    const response = await api.put(`/api/automation-configs/system/0/${authorityNamespace}`, { payload: config })

    return {
      namespace,
      config: response.data.data.payload as Record<string, unknown>,
      meta: {
        defaults: response.data.data.payload as Record<string, unknown>,
        field_catalog: [],
      },
    } as SettingsNamespacePayload
  }

  async function resetNamespace(namespace: string): Promise<SettingsNamespacePayload> {
    return getNamespace(namespace)
  }

  return {
    getAll,
    getNamespace,
    updateNamespace,
    resetNamespace,
  }
}
