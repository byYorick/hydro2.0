/**
 * Унифицированный composable проверки готовности зоны к запуску.
 *
 * Используется Setup Wizard и Growth Cycle Wizard — оба вызывают
 * `GET /zones/{id}/health` и ожидают один и тот же ZoneLaunchReadiness.
 */

import { ref, type Ref } from 'vue'
import { api } from '@/services/api'

export interface ZoneLaunchReadiness {
  ready: boolean
  checked?: boolean
  errors?: string[]
  checks?: Record<string, boolean>
  warnings?: string[]
  error_details?: Array<Record<string, unknown>>
  blocking_alerts?: Array<Record<string, unknown>>
  dispatch_enabled?: boolean
}

interface ZoneHealthResponse {
  readiness?: ZoneLaunchReadiness | null
}

export interface UseZoneReadiness {
  readiness: Ref<ZoneLaunchReadiness | null>
  loading: Ref<boolean>
  load: (zoneId: number | null) => Promise<void>
  reset: () => void
}

export function useZoneReadiness(): UseZoneReadiness {
  const readiness = ref<ZoneLaunchReadiness | null>(null)
  const loading = ref(false)

  async function load(zoneId: number | null): Promise<void> {
    if (!zoneId) {
      readiness.value = null
      loading.value = false
      return
    }

    loading.value = true

    try {
      const payload = await api.zones.getHealth<ZoneHealthResponse | ZoneLaunchReadiness | null>(zoneId)
      readiness.value =
        (payload as ZoneHealthResponse | null)?.readiness
        ?? (payload as ZoneLaunchReadiness | null)
    } catch {
      readiness.value = null
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    readiness.value = null
    loading.value = false
  }

  return { readiness, loading, load, reset }
}
