import { computed, onMounted, onUnmounted, ref, shallowRef, type Ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { useTelemetry } from '@/composables/useTelemetry'
import { useWebSocket } from '@/composables/useWebSocket'
import { logger } from '@/utils/logger'
import type { Alert, EventKind, ZoneEvent } from '@/types'

type TelemetryPeriod = '1h' | '24h' | '7d'
type TelemetryMetricKey = 'ph' | 'ec' | 'temperature' | 'humidity'

interface TelemetryMiniChartState {
  data: Array<{ ts: number; value?: number | null; avg?: number | null; min?: number | null; max?: number | null }>
  currentValue: number | null
  loading: boolean
}

interface AlertWithDetails extends Alert {
  details?: {
    message?: string
  } | null
}

interface AggregatePoint {
  ts: string | number
  value?: number | null
  avg?: number | null
  min?: number | null
  max?: number | null
}

interface RealtimeDashboardEvent {
  id: number
  kind: EventKind
  message: string
  zoneId?: number
  occurredAt: string
}

function normalizeEventKind(kind: string): EventKind {
  if (kind === 'ALERT' || kind === 'WARNING' || kind === 'INFO' || kind === 'SUCCESS') {
    return kind
  }

  return 'INFO'
}

interface UseDashboardRealtimeFeedOptions {
  theme: Ref<unknown>
  selectedZoneId: Ref<number | null>
  telemetryPeriod: Ref<TelemetryPeriod>
  latestAlerts: Ref<Alert[]>
}

export function useDashboardRealtimeFeed({
  theme,
  selectedZoneId,
  telemetryPeriod,
  latestAlerts,
}: UseDashboardRealtimeFeedOptions): {
  eventFilter: Ref<'ALL' | EventKind>
  filteredEvents: Ref<Array<ZoneEvent & { created_at?: string }>>
  telemetryMetrics: Ref<Array<{
    key: string
    label: string
    data: Array<{ ts: number; value?: number | null; avg?: number | null; min?: number | null; max?: number | null }>
    currentValue?: number
    unit: string
    loading: boolean
    color: string
  }>>
  handleOpenDetail: (zoneId: number, metric: string) => void
  loadTelemetryMetrics: () => Promise<void>
  resetTelemetryData: () => void
} {
  const { fetchAggregates } = useTelemetry()
  const { subscribeToGlobalEvents } = useWebSocket()

  const telemetryMetricKeys: TelemetryMetricKey[] = ['ph', 'ec', 'temperature', 'humidity']

  const telemetryData = shallowRef<Record<TelemetryMetricKey, TelemetryMiniChartState>>({
    ph: { data: [], currentValue: null, loading: false },
    ec: { data: [], currentValue: null, loading: false },
    temperature: { data: [], currentValue: null, loading: false },
    humidity: { data: [], currentValue: null, loading: false },
  })

  const events = shallowRef<Array<ZoneEvent & { created_at?: string }>>([])
  const eventFilter = ref<'ALL' | EventKind>('ALL')

  const propsEvents = computed(() => {
    return (latestAlerts.value || []).map(a => ({
      id: a.id,
      kind: 'ALERT' as const,
      message: (a as AlertWithDetails).details?.message || a.type,
      zone_id: a.zone_id,
      occurred_at: a.created_at,
      created_at: a.created_at,
    }))
  })

  const allEvents = computed(() => {
    return [...events.value, ...propsEvents.value]
      .sort((a, b) => {
        const timeA = new Date(a.occurred_at || a.created_at || 0).getTime()
        const timeB = new Date(b.occurred_at || b.created_at || 0).getTime()
        return timeB - timeA
      })
      .slice(0, 20)
  })

  const filteredEvents = computed(() => {
    if (eventFilter.value === 'ALL') {
      return allEvents.value
    }
    return allEvents.value.filter(e => e.kind === eventFilter.value)
  })

  function handleOpenDetail(zoneId: number, _metric: string): void {
    if (!zoneId) {
      return
    }

    router.visit(`/zones/${zoneId}`, {
      preserveUrl: false,
    })
  }

  const resolveCssColor = (variable: string, fallback: string): string => {
    if (typeof window === 'undefined') {
      return fallback
    }
    const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
    return value || fallback
  }

  const telemetryPalette = computed(() => {
    theme.value
    return {
      ph: resolveCssColor('--accent-cyan', '#3b82f6'),
      ec: resolveCssColor('--accent-green', '#10b981'),
      temperature: resolveCssColor('--accent-amber', '#f59e0b'),
      humidity: resolveCssColor('--accent-lime', '#8b5cf6'),
    }
  })

  const telemetryMetrics = computed(() => {
    const data = telemetryData.value
    const palette = telemetryPalette.value

    return [
      {
        key: 'ph',
        label: 'pH',
        data: data.ph.data,
        currentValue: data.ph.currentValue === null ? undefined : data.ph.currentValue,
        unit: '',
        loading: data.ph.loading,
        color: palette.ph,
      },
      {
        key: 'ec',
        label: 'EC',
        data: data.ec.data,
        currentValue: data.ec.currentValue === null ? undefined : data.ec.currentValue,
        unit: 'мСм/см',
        loading: data.ec.loading,
        color: palette.ec,
      },
      {
        key: 'temperature',
        label: 'Температура',
        data: data.temperature.data,
        currentValue: data.temperature.currentValue === null ? undefined : data.temperature.currentValue,
        unit: '°C',
        loading: data.temperature.loading,
        color: palette.temperature,
      },
      {
        key: 'humidity',
        label: 'Влажность',
        data: data.humidity.data,
        currentValue: data.humidity.currentValue === null ? undefined : data.humidity.currentValue,
        unit: '%',
        loading: data.humidity.loading,
        color: palette.humidity,
      },
    ]
  })

  function resetTelemetryData(): void {
    telemetryMetricKeys.forEach(metric => {
      telemetryData.value[metric].data = []
      telemetryData.value[metric].currentValue = null
      telemetryData.value[metric].loading = false
    })
  }

  async function loadTelemetryMetrics(): Promise<void> {
    const zoneId = selectedZoneId.value
    const period = telemetryPeriod.value

    if (!zoneId) {
      resetTelemetryData()
      return
    }

    for (const metric of telemetryMetricKeys) {
      telemetryData.value[metric].loading = true
      try {
        const data = (await fetchAggregates(zoneId, metric, period)) as AggregatePoint[]
        if (selectedZoneId.value !== zoneId || telemetryPeriod.value !== period) {
          continue
        }

        telemetryData.value[metric].data = data.map(item => ({
          ts: new Date(item.ts).getTime(),
          value: item.value ?? undefined,
          avg: item.avg ?? undefined,
          min: item.min ?? undefined,
          max: item.max ?? undefined,
        }))

        if (data.length > 0) {
          telemetryData.value[metric].currentValue =
            data[data.length - 1].value ?? data[data.length - 1].avg ?? null
        }
      } catch (err) {
        logger.error(`[Dashboard] Failed to load ${metric} telemetry:`, err)
      } finally {
        telemetryData.value[metric].loading = false
      }
    }
  }

  let unsubscribeGlobalEvents: (() => void) | null = null

  onMounted(async () => {
    const { useBatchUpdates } = await import('@/composables/useOptimizedUpdates')
    const { add: addEvent } = useBatchUpdates<RealtimeDashboardEvent>(
      (eventBatch) => {
        eventBatch.forEach(event => {
          events.value.unshift({
            id: event.id,
            kind: event.kind,
            message: event.message,
            zone_id: event.zoneId,
            occurred_at: event.occurredAt,
            created_at: event.occurredAt,
          })
        })

        if (events.value.length > 20) {
          events.value = events.value.slice(0, 20)
        }
      },
      { debounceMs: 200, maxBatchSize: 5, maxWaitMs: 1000 }
    )

    unsubscribeGlobalEvents = subscribeToGlobalEvents((event) => {
      const normalizedId = typeof event.id === 'number'
        ? event.id
        : Number.parseInt(String(event.id ?? 0), 10)
      if (!Number.isFinite(normalizedId)) {
        return
      }

      addEvent({
        id: normalizedId,
        kind: normalizeEventKind(event.kind),
        message: event.message,
        zoneId: event.zoneId,
        occurredAt: event.occurredAt,
      })
    })
  })

  onUnmounted(() => {
    if (unsubscribeGlobalEvents) {
      unsubscribeGlobalEvents()
      unsubscribeGlobalEvents = null
    }
  })

  return {
    eventFilter,
    filteredEvents,
    telemetryMetrics,
    handleOpenDetail,
    loadTelemetryMetrics,
    resetTelemetryData,
  }
}
