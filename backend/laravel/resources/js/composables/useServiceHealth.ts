/**
 * Composable для service health pills в LaunchTopBar (mqtt-bridge / history-logger / AE3).
 *
 * Использует TanStack Query (refetch каждые 15с), читает из existing
 * `/api/system/health` через типизированный `systemApi.health()`.
 *
 * Маппинг raw-статусов backend → UI tone:
 *   'ok'      → online   (growth chip)
 *   'fail'    → offline  (alert chip)
 *   'unknown' → unknown  (neutral chip)
 *   *         → degraded (warn chip)
 */
import { computed, type ComputedRef } from 'vue'
import { useQuery, type UseQueryReturnType } from '@tanstack/vue-query'
import { systemApi, type SystemHealthPayload } from '@/services/api/system'

export type ServiceStatus = 'online' | 'degraded' | 'offline' | 'unknown'

export interface ServiceHealthPill {
  key: string
  label: string
  status: ServiceStatus
}

export function mapServiceStatus(raw: string | undefined | null): ServiceStatus {
  if (raw === 'ok') return 'online'
  if (raw === 'fail') return 'offline'
  if (raw === 'unknown' || raw == null) return 'unknown'
  return 'degraded'
}

export interface UseServiceHealthReturn {
  query: UseQueryReturnType<SystemHealthPayload, Error>
  pills: ComputedRef<ServiceHealthPill[]>
}

export function useServiceHealth(): UseServiceHealthReturn {
  const query = useQuery<SystemHealthPayload>({
    queryKey: ['system', 'health'],
    queryFn: () => systemApi.health(),
    staleTime: 15_000,
    refetchInterval: 15_000,
  })

  const pills = computed<ServiceHealthPill[]>(() => {
    const data = query.data.value
    return [
      {
        key: 'automation_engine',
        label: 'AE3',
        status: mapServiceStatus(data?.automation_engine as string | undefined),
      },
      {
        key: 'history_logger',
        label: 'history-logger',
        status: mapServiceStatus(data?.history_logger as string | undefined),
      },
      {
        key: 'mqtt',
        label: 'mqtt-bridge',
        status: mapServiceStatus(data?.mqtt as string | undefined),
      },
    ]
  })

  return { query, pills }
}
