import { computed, type Ref } from 'vue'

export type SimulationJobStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed'

export interface SimulationReportPhase {
  phase_id?: number | null
  phase_index?: number | null
  name?: string | null
  started_at?: string | null
  completed_at?: string | null
  status?: string | null
}

interface SimulationResultsLike {
  duration_hours?: number
  step_minutes?: number
}

interface SimulationFormLike {
  duration_hours: number
  step_minutes: number
}

interface SimulationReportLike {
  summary_json?: Record<string, unknown> | null
  phases_json?: SimulationReportPhase[] | null
  metrics_json?: Record<string, unknown> | null
  errors_json?: unknown
}

interface UseSimulationPresentationParams {
  simulationProgressValue: Ref<number | null>
  simulationStatus: Ref<SimulationJobStatus>
  simulationElapsedMinutes: Ref<number | null>
  simulationRealDurationMinutes: Ref<number | null>
  simulationEngine: Ref<string | null>
  simulationMode: Ref<string | null>
  simulationProgressSource: Ref<string | null>
  simulationCurrentPhase: Ref<string | null>
  simulationSimNow: Ref<string | null>
  simulationReport: Ref<SimulationReportLike | null>
  loading: Ref<boolean>
  results: Ref<SimulationResultsLike | null>
  form: SimulationFormLike
}

export function mapActiveSimulationStatus(
  status?: string | null
): Exclude<SimulationJobStatus, 'idle'> | null {
  if (!status) return null
  const normalized = status.toLowerCase()
  if (normalized === 'pending') return 'queued'
  if (normalized === 'running') return 'processing'
  if (normalized === 'completed') return 'completed'
  if (normalized === 'failed') return 'failed'
  return 'processing'
}

export function useSimulationPresentation(params: UseSimulationPresentationParams) {
  const simulationProgress = computed(() => {
    if (params.simulationProgressValue.value !== null) {
      return Math.round(params.simulationProgressValue.value * 100)
    }
    switch (params.simulationStatus.value) {
      case 'queued':
        return 20
      case 'processing':
        return 60
      case 'completed':
        return 100
      case 'failed':
        return 100
      default:
        return 0
    }
  })

  const simulationProgressDetails = computed(() => {
    if (params.simulationProgressValue.value === null) return null
    const percent = Math.round(params.simulationProgressValue.value * 100)
    if (params.simulationElapsedMinutes.value !== null && params.simulationRealDurationMinutes.value !== null) {
      const remaining = Math.max(
        0,
        Math.round((params.simulationRealDurationMinutes.value - params.simulationElapsedMinutes.value) * 100) / 100
      )
      return `Прогресс: ${percent}% (${params.simulationElapsedMinutes.value} / ${params.simulationRealDurationMinutes.value} мин, осталось ${remaining} мин)`
    }
    return `Прогресс: ${percent}%`
  })

  const simulationEngineLabel = computed(() => {
    if (!params.simulationEngine.value && !params.simulationMode.value) return null
    const engine = params.simulationEngine.value ? params.simulationEngine.value.replace('_', ' ') : 'unknown'
    return params.simulationMode.value ? `${engine} (${params.simulationMode.value})` : engine
  })

  const simulationProgressSourceLabel = computed(() => {
    if (!params.simulationProgressSource.value) return null
    if (params.simulationProgressSource.value === 'actions') return 'действия'
    if (params.simulationProgressSource.value === 'timer') return 'таймер'
    return params.simulationProgressSource.value
  })

  const simulationCurrentPhaseLabel = computed(() => {
    if (!params.simulationCurrentPhase.value) return null
    return String(params.simulationCurrentPhase.value)
  })

  const simulationSimTimeLabel = computed(() => {
    if (!params.simulationSimNow.value) return null
    const parsed = new Date(params.simulationSimNow.value)
    if (Number.isNaN(parsed.getTime())) {
      return `Сим-время: ${params.simulationSimNow.value}`
    }
    return `Сим-время: ${parsed.toLocaleString()}`
  })

  const simulationStatusLabel = computed(() => {
    switch (params.simulationStatus.value) {
      case 'queued':
        return 'В очереди'
      case 'processing':
        return 'Выполняется'
      case 'completed':
        return 'Завершено'
      case 'failed':
        return 'Ошибка'
      default:
        return ''
    }
  })

  const reportSummaryEntries = computed(() => {
    const summary = params.simulationReport.value?.summary_json
    if (!summary || typeof summary !== 'object') return []
    return Object.entries(summary)
      .map(([key, value]) => ({ key, value }))
      .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== '')
  })

  const reportPhaseEntries = computed<SimulationReportPhase[]>(() => {
    const phases = params.simulationReport.value?.phases_json
    if (!Array.isArray(phases)) return []
    return phases as SimulationReportPhase[]
  })

  const reportMetricsEntries = computed(() => {
    const metrics = params.simulationReport.value?.metrics_json
    if (!metrics || typeof metrics !== 'object') return []
    return Object.entries(metrics)
      .map(([key, value]) => ({ key, value }))
      .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== '')
  })

  const reportErrors = computed(() => {
    const errors = params.simulationReport.value?.errors_json
    if (!errors) return []
    if (Array.isArray(errors)) return errors
    return [errors]
  })

  const isSimulating = computed(() => {
    return params.simulationStatus.value === 'queued' || params.simulationStatus.value === 'processing' || params.loading.value
  })

  const resultDurationHours = computed(() => {
    return params.results.value?.duration_hours ?? params.form.duration_hours
  })

  const resultStepMinutes = computed(() => {
    return params.results.value?.step_minutes ?? params.form.step_minutes
  })

  return {
    simulationProgress,
    simulationProgressDetails,
    simulationEngineLabel,
    simulationProgressSourceLabel,
    simulationCurrentPhaseLabel,
    simulationSimTimeLabel,
    simulationStatusLabel,
    reportSummaryEntries,
    reportPhaseEntries,
    reportMetricsEntries,
    reportErrors,
    isSimulating,
    resultDurationHours,
    resultStepMinutes,
  }
}
