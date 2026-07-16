import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { useTelemetry } from '@/composables/useTelemetry'
import { useCycleCenterActions } from '@/composables/useCycleCenterActions'
import {
  useCycleCenterView,
  type Greenhouse,
  type ZoneSummary,
} from '@/composables/useCycleCenterView'
import { useWebSocket } from '@/composables/useWebSocket'

/** Throttle Inertia partial reload of dashboard zone cards (5–15s band). */
export const DASHBOARD_ZONES_RELOAD_THROTTLE_MS = 10_000

/** Sparkline series cache TTL — avoid forever-stale mini-charts on zone cards. */
export const SPARKLINE_CACHE_TTL_MS = 90_000

export interface ZoneTargetRange {
  min: number | null
  max: number | null
}

export interface UnifiedSummary {
  zones_total: number
  zones_running: number
  zones_warning: number
  zones_alarm: number
  /** Зоны, где AE3 остановлен ACTIVE-алертом из AlertPolicyService::POLICY_MANAGED_CODES. */
  zones_blocked?: number
  cycles_running: number
  cycles_paused: number
  cycles_planned: number
  cycles_none: number
  devices_online: number
  devices_total: number
  alerts_active: number
  greenhouses_count: number
}

export interface UnifiedZone extends ZoneSummary {
  targets: {
    ph: ZoneTargetRange | null
    ec: ZoneTargetRange | null
    temperature: ZoneTargetRange | null
  }
  crop: string | null
}

export interface ZoneSparklineSeries {
  ph: number[] | null
  ec: number[] | null
  temperature: number[] | null
}

type ToastLike = Parameters<typeof useCycleCenterActions>[0]['showToast']

export function isSparklineCacheFresh(
  fetchedAt: number | undefined,
  now: number,
  ttlMs: number = SPARKLINE_CACHE_TTL_MS,
): boolean {
  return fetchedAt != null && now - fetchedAt < ttlMs
}

/**
 * Leading + trailing coalesce: first call runs ASAP, further calls within the
 * window schedule a single run at the end of the remaining throttle interval.
 */
export function createThrottledTask(
  run: () => void | Promise<void>,
  throttleMs: number,
): { schedule: () => void; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastRunAt = 0

  const schedule = (): void => {
    if (timer != null) {
      return
    }

    const elapsed = Date.now() - lastRunAt
    const delay = lastRunAt === 0 || elapsed >= throttleMs ? 0 : throttleMs - elapsed

    timer = setTimeout(() => {
      timer = null
      lastRunAt = Date.now()
      void run()
    }, delay)
  }

  const cancel = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  return { schedule, cancel }
}

export function useUnifiedDashboard(options: {
  zones: Ref<UnifiedZone[]>
  showToast: ToastLike
}): ReturnType<typeof useCycleCenterView> & ReturnType<typeof useCycleCenterActions> & {
  sparklines: Ref<Record<number, ZoneSparklineSeries>>
  sparklineColor: (zone: UnifiedZone) => string
  reloadUnified: () => Promise<void>
} {
  const { fetchHistory } = useTelemetry()
  const { subscribeToGlobalEvents, subscribeToAlerts } = useWebSocket()
  const sparklines = ref<Record<number, ZoneSparklineSeries>>({})
  const sparklineFetchedAt = ref<Record<number, number>>({})

  const zonesAsSummary = computed(() => options.zones.value as ZoneSummary[])

  function invalidateSparklineCache(): void {
    sparklineFetchedAt.value = {}
  }

  async function reloadUnified(): Promise<void> {
    invalidateSparklineCache()
    await router.reload({ only: ['summary', 'zones', 'greenhouses', 'latestAlerts'] })
  }

  const view = useCycleCenterView({ zones: zonesAsSummary, statusFilterMode: 'zone' })
  const actions = useCycleCenterActions({
    showToast: options.showToast,
    reloadCenter: reloadUnified,
  })

  function loadSparklinesForZones(zones: UnifiedZone[]): void {
    const now = Date.now()
    zones.forEach((zone, i) => {
      if (isSparklineCacheFresh(sparklineFetchedAt.value[zone.id], now)) {
        return
      }
      setTimeout(async () => {
        try {
          const rangeNow = new Date()
          const from = new Date(rangeNow.getTime() - 24 * 60 * 60 * 1000)
          const range = { from: from.toISOString(), to: rangeNow.toISOString() }
          const [phHist, ecHist, tempHist] = await Promise.all([
            fetchHistory(zone.id, 'PH', range).catch(() => []),
            fetchHistory(zone.id, 'EC', range).catch(() => []),
            fetchHistory(zone.id, 'TEMPERATURE', range).catch(() => []),
          ])
          sparklines.value = {
            ...sparklines.value,
            [zone.id]: {
              ph: phHist.length > 0 ? phHist.map((p) => p.value) : null,
              ec: ecHist.length > 0 ? ecHist.map((p) => p.value) : null,
              temperature: tempHist.length > 0 ? tempHist.map((p) => p.value) : null,
            },
          }
          sparklineFetchedAt.value = {
            ...sparklineFetchedAt.value,
            [zone.id]: Date.now(),
          }
        } catch {
          /* non-critical */
        }
      }, i * 200)
    })
  }

  watch(
    view.pagedZones,
    (z) => {
      loadSparklinesForZones(z as UnifiedZone[])
    },
    { immediate: true },
  )

  function sparklineColor(zone: UnifiedZone): string {
    if (zone.status === 'ALARM') {
      return 'var(--accent-red)'
    }
    if (zone.status === 'WARNING') {
      return 'var(--accent-amber)'
    }
    return 'var(--accent-cyan)'
  }

  const { schedule: scheduleZonesReload, cancel: cancelZonesReload } = createThrottledTask(
    reloadUnified,
    DASHBOARD_ZONES_RELOAD_THROTTLE_MS,
  )

  let unsubscribeGlobalEvents: (() => void) | null = null
  let unsubscribeAlerts: (() => void) | null = null

  onMounted(() => {
    // Global feed events (workflow / zone state / actions) + alerts channel.
    // Live event sidebar stays in useDashboardRealtimeFeed; this only refreshes cards.
    unsubscribeGlobalEvents = subscribeToGlobalEvents(() => {
      scheduleZonesReload()
    })
    unsubscribeAlerts = subscribeToAlerts(() => {
      scheduleZonesReload()
    })
  })

  onUnmounted(() => {
    cancelZonesReload()
    if (unsubscribeGlobalEvents) {
      unsubscribeGlobalEvents()
      unsubscribeGlobalEvents = null
    }
    if (unsubscribeAlerts) {
      unsubscribeAlerts()
      unsubscribeAlerts = null
    }
  })

  return {
    ...view,
    ...actions,
    sparklines,
    sparklineColor,
    reloadUnified,
  }
}

export type { Greenhouse }
