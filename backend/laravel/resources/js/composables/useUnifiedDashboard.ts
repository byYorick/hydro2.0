import { computed, ref, watch, type Ref } from 'vue'
import { router } from '@inertiajs/vue3'
import { useTelemetry } from '@/composables/useTelemetry'
import { useCycleCenterActions } from '@/composables/useCycleCenterActions'
import {
  useCycleCenterView,
  type Greenhouse,
  type ZoneSummary,
} from '@/composables/useCycleCenterView'

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

export function useUnifiedDashboard(options: {
  zones: Ref<UnifiedZone[]>
  showToast: ToastLike
}): ReturnType<typeof useCycleCenterView> & ReturnType<typeof useCycleCenterActions> & {
  sparklines: Ref<Record<number, ZoneSparklineSeries>>
  sparklineColor: (zone: UnifiedZone) => string
  reloadUnified: () => Promise<void>
} {
  const { fetchHistory } = useTelemetry()
  const sparklines = ref<Record<number, ZoneSparklineSeries>>({})

  const zonesAsSummary = computed(() => options.zones.value as ZoneSummary[])

  async function reloadUnified(): Promise<void> {
    await router.reload({ only: ['summary', 'zones', 'greenhouses', 'latestAlerts'] })
  }

  const view = useCycleCenterView({ zones: zonesAsSummary, statusFilterMode: 'zone' })
  const actions = useCycleCenterActions({
    showToast: options.showToast,
    reloadCenter: reloadUnified,
  })

  function loadSparklinesForZones(zones: UnifiedZone[]): void {
    zones.forEach((zone, i) => {
      if (sparklines.value[zone.id]) {
        return
      }
      setTimeout(async () => {
        try {
          const now = new Date()
          const from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
          const range = { from: from.toISOString(), to: now.toISOString() }
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

  return {
    ...view,
    ...actions,
    sparklines,
    sparklineColor,
    reloadUnified,
  }
}

export type { Greenhouse }
