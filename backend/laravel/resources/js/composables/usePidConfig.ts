/**
 * Composable для работы с PID конфигами
 */
import { ref, type Ref } from 'vue'
import { api } from '@/services/api'
import type { ToastHandler } from '@/services/api'
import { useErrorHandler } from './useErrorHandler'
import type {
  PidConfig,
  PidConfigRecord,
  PidConfigWithMeta,
  PidLog,
  PumpCalibration,
  RelayAutotuneStatus,
} from '@/types/PidConfig'

const PID_NAMESPACE_MAP: Record<'ph' | 'ec', string> = {
  ph: 'zone.pid.ph',
  ec: 'zone.pid.ec',
}

export function usePidConfig(showToast?: ToastHandler) {
  const { handleError } = useErrorHandler(showToast)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)

  async function getPidConfig(zoneId: number, type: 'ph' | 'ec'): Promise<PidConfigWithMeta | null> {
    loading.value = true
    error.value = null

    try {
      const document = await api.automationConfigs.get<{ payload: PidConfig } | null>(
        'zone',
        zoneId,
        PID_NAMESPACE_MAP[type],
      )

      if (!document || typeof document !== 'object' || !('payload' in document)) {
        return null
      }

      return {
        type,
        config: document.payload,
        updated_by: null,
        updated_at: null,
        is_default: false,
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getAllPidConfigs(zoneId: number): Promise<PidConfigRecord> {
    loading.value = true
    error.value = null

    try {
      const [ph, ec] = await Promise.all([
        getPidConfig(zoneId, 'ph'),
        getPidConfig(zoneId, 'ec'),
      ])

      return { ph, ec }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updatePidConfig(
    zoneId: number,
    type: 'ph' | 'ec',
    config: PidConfig
  ): Promise<PidConfigWithMeta> {
    loading.value = true
    error.value = null

    try {
      const document = await api.automationConfigs.update<{ payload: PidConfig }>(
        'zone',
        zoneId,
        PID_NAMESPACE_MAP[type],
        config as unknown as Record<string, unknown>,
      )

      return {
        type,
        config: document.payload,
        updated_by: null,
        updated_at: null,
        is_default: false,
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

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
      const payload = await api.zones.getPidLogs<{
        data?: PidLog[]
        meta?: { total: number; limit: number; offset: number }
      } | PidLog[]>(zoneId, options)

      const logs = Array.isArray(payload)
        ? payload
        : Array.isArray(payload?.data) ? payload.data : []
      const meta = (payload && !Array.isArray(payload) ? payload.meta : null) ?? {
        total: logs.length,
        limit: options?.limit ?? logs.length,
        offset: options?.offset ?? 0,
      }

      return {
        logs,
        total: meta.total,
        limit: meta.limit,
        offset: meta.offset,
      }
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getPumpCalibrations(zoneId: number): Promise<PumpCalibration[]> {
    loading.value = true
    error.value = null

    try {
      const payload = await api.zones.getPumpCalibrations<PumpCalibration[] | { data?: PumpCalibration[] }>(zoneId)
      if (Array.isArray(payload)) return payload
      if (payload && Array.isArray(payload.data)) return payload.data
      return []
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function updatePumpCalibration(
    zoneId: number,
    channelId: number,
    payload: {
      ml_per_sec: number
      k_ms_per_ml_l?: number | null
    }
  ): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await api.zones.updatePumpCalibration(zoneId, channelId, payload)
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function startRelayAutotune(zoneId: number, pidType: 'ph' | 'ec'): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await api.zones.startRelayAutotune(zoneId, { pid_type: pidType })
    } catch (err) {
      error.value = err instanceof Error ? err : new Error('Unknown error')
      handleError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getRelayAutotuneStatus(zoneId: number, pidType: 'ph' | 'ec'): Promise<RelayAutotuneStatus> {
    loading.value = true
    error.value = null

    try {
      const payload = await api.zones.getRelayAutotuneStatus<RelayAutotuneStatus | { data?: RelayAutotuneStatus }>(
        zoneId,
        { pid_type: pidType },
      )

      const candidate = payload && !Array.isArray(payload) && 'data' in (payload as Record<string, unknown>)
        ? (payload as { data?: RelayAutotuneStatus }).data
        : (payload as RelayAutotuneStatus | null)

      if (candidate) {
        return candidate
      }

      return {
        zone_id: zoneId,
        pid_type: pidType,
        status: 'idle',
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
    getPumpCalibrations,
    updatePumpCalibration,
    startRelayAutotune,
    getRelayAutotuneStatus,
  }
}
