import { computed, ref, watch, type Ref } from 'vue'

export interface Greenhouse {
  id: number
  name: string
}

export interface CycleStage {
  name?: string
  code?: string
  started_at?: string | null
}

export interface CycleProgress {
  overall_pct?: number
  stage_pct?: number
}

export interface GrowCycle {
  id: number
  status: string
  planting_at?: string | null
  expected_harvest_at?: string | null
  current_stage?: CycleStage | null
  progress?: CycleProgress
}

export interface ZoneTelemetry {
  ph: number | null
  ec: number | null
  temperature: number | null
  humidity: number | null
  co2: number | null
  updated_at: string | null
}

export interface ZoneSummary {
  id: number
  name: string
  status: string
  greenhouse: Greenhouse | null
  telemetry: ZoneTelemetry
  alerts_count: number
  alerts_preview: Array<{ id: number; type: string; details: string; created_at: string }>
  devices: { total: number; online: number }
  recipe: { id: number; name: string } | null
  plant: { id: number; name: string } | null
  cycle: GrowCycle | null
}

export interface Summary {
  zones_total: number
  cycles_running: number
  cycles_paused: number
  cycles_planned: number
  cycles_none: number
  alerts_active: number
  devices_online: number
  devices_total: number
}

interface UseCycleCenterViewOptions {
  zones: Ref<ZoneSummary[]>
}

export function useCycleCenterView({ zones }: UseCycleCenterViewOptions) {
  const query = ref('')
  const statusFilter = ref('')
  const greenhouseFilter = ref('')
  const showOnlyAlerts = ref(false)
  const denseView = ref(false)
  const currentPage = ref(1)
  const perPage = ref(8)

  const filteredZones = computed(() => {
    const search = query.value.trim().toLowerCase()
    return zones.value.filter((zone) => {
      const matchesSearch = !search || [
        zone.name,
        zone.greenhouse?.name,
        zone.recipe?.name,
        zone.plant?.name,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(search))

      const cycleStatus = zone.cycle?.status || 'NONE'
      const matchesStatus = !statusFilter.value || statusFilter.value === cycleStatus
      const matchesGreenhouse = !greenhouseFilter.value || String(zone.greenhouse?.id || '') === greenhouseFilter.value
      const matchesAlerts = !showOnlyAlerts.value || zone.alerts_count > 0

      return matchesSearch && matchesStatus && matchesGreenhouse && matchesAlerts
    })
  })

  const pagedZones = computed(() => {
    const start = (currentPage.value - 1) * perPage.value
    return filteredZones.value.slice(start, start + perPage.value)
  })

  watch([query, statusFilter, greenhouseFilter, showOnlyAlerts], () => {
    currentPage.value = 1
  })

  function toggleDense(): void {
    denseView.value = !denseView.value
    perPage.value = denseView.value ? 12 : 8
  }

  function formatMetric(value: number | null, digits: number): string {
    if (value === null || value === undefined) {
      return '—'
    }
    return Number(value).toFixed(digits)
  }

  function formatDate(value: string): string {
    const date = new Date(value)
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short' }).format(date)
  }

  function formatTime(value: string): string {
    const date = new Date(value)
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date)
  }

  function getZoneStatusVariant(status: string): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
    switch (status) {
      case 'RUNNING':
        return 'success'
      case 'PAUSED':
        return 'info'
      case 'WARNING':
        return 'warning'
      case 'ALARM':
        return 'danger'
      default:
        return 'neutral'
    }
  }

  return {
    query,
    statusFilter,
    greenhouseFilter,
    showOnlyAlerts,
    denseView,
    currentPage,
    perPage,
    filteredZones,
    pagedZones,
    toggleDense,
    formatMetric,
    formatDate,
    formatTime,
    getZoneStatusVariant,
  }
}
