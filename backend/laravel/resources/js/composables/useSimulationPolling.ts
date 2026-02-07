import { watch, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { mapActiveSimulationStatus } from '@/composables/useSimulationPresentation'
import type { SimulationRuntimeStatus } from '@/composables/useSimulationSubmit'

interface ApiClient {
  get<T = unknown>(url: string, config?: Record<string, unknown>): Promise<{ data?: T }>
}

interface SimulationStatusResponse {
  status?: string
  data?: unknown
}

interface UseSimulationPollingParams<SimulationResults, SimulationReport, SimulationAction, SimulationPidStatus> {
  api: ApiClient
  simulationJobId: Ref<string | null>
  simulationStatus: Ref<SimulationRuntimeStatus>
  simulationProgressValue: Ref<number | null>
  simulationElapsedMinutes: Ref<number | null>
  simulationRealDurationMinutes: Ref<number | null>
  simulationSimNow: Ref<string | null>
  simulationEngine: Ref<string | null>
  simulationMode: Ref<string | null>
  simulationProgressSource: Ref<string | null>
  simulationActions: Ref<SimulationAction[]>
  simulationPidStatuses: Ref<SimulationPidStatus[]>
  simulationCurrentPhase: Ref<string | null>
  simulationReport: Ref<SimulationReport | null>
  simulationDbId: Ref<number | null>
  simulationEvents: Ref<unknown[]>
  simulationEventsLoading: Ref<boolean>
  attachSimulation: (simulationId: number) => void
  loadSimulationEvents: (simulationId: number) => Promise<void>
  normalizeSimulationResult: (payload: unknown) => SimulationResults | null
  results: Ref<SimulationResults | null>
  error: Ref<string | null>
  stopLoading: () => void
  activeSimulationId: Ref<number | null | undefined>
  activeSimulationStatus: Ref<string | null | undefined>
  isVisible: Ref<boolean>
  loading: Ref<boolean>
}

function clampProgress(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function toFiniteNumberOrNull(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null
  }
  return value
}

export function useSimulationPolling<
  SimulationResults,
  SimulationReport,
  SimulationAction,
  SimulationPidStatus,
>(params: UseSimulationPollingParams<SimulationResults, SimulationReport, SimulationAction, SimulationPidStatus>) {
  let simulationPollTimer: ReturnType<typeof setInterval> | null = null

  const clearSimulationPolling = (): void => {
    if (simulationPollTimer) {
      clearInterval(simulationPollTimer)
      simulationPollTimer = null
    }
  }

  const pollSimulationStatus = async (jobId: string): Promise<void> => {
    try {
      const response = await params.api.get<SimulationStatusResponse>(`/simulations/${jobId}`)
      const data = response.data?.data
      if (!data || typeof data !== 'object') return
      const payload = data as Record<string, unknown>

      const statusValue = payload.status
      if (typeof statusValue === 'string') {
        params.simulationStatus.value = statusValue as SimulationRuntimeStatus
      }

      const parsedSimId = Number(payload.simulation_id)
      if (Number.isFinite(parsedSimId) && parsedSimId > 0) {
        if (params.simulationDbId.value !== parsedSimId) {
          params.attachSimulation(parsedSimId)
        } else if (!params.simulationEvents.value.length && !params.simulationEventsLoading.value) {
          void params.loadSimulationEvents(parsedSimId)
        }
      }

      const simulation = payload.simulation
      if (simulation && typeof simulation === 'object') {
        const simulationObject = simulation as Record<string, unknown>
        params.simulationEngine.value = typeof simulationObject.engine === 'string' ? simulationObject.engine : null
        params.simulationMode.value = typeof simulationObject.mode === 'string' ? simulationObject.mode : null
      } else {
        params.simulationEngine.value = null
        params.simulationMode.value = null
      }

      params.simulationProgressSource.value = typeof payload.progress_source === 'string' ? payload.progress_source : null
      params.simulationActions.value = Array.isArray(payload.actions) ? (payload.actions as SimulationAction[]) : []
      params.simulationPidStatuses.value = Array.isArray(payload.pid_statuses)
        ? (payload.pid_statuses as SimulationPidStatus[])
        : []
      params.simulationCurrentPhase.value = payload.current_phase ? String(payload.current_phase) : null
      params.simulationReport.value = payload.report && typeof payload.report === 'object'
        ? (payload.report as SimulationReport)
        : null

      const progress = toFiniteNumberOrNull(payload.progress)
      params.simulationProgressValue.value = progress === null ? null : clampProgress(progress)

      const elapsedMinutes = toFiniteNumberOrNull(payload.elapsed_minutes)
      params.simulationElapsedMinutes.value = elapsedMinutes === null
        ? null
        : Math.round(elapsedMinutes * 100) / 100

      const realDurationMinutes = toFiniteNumberOrNull(payload.real_duration_minutes)
      params.simulationRealDurationMinutes.value = realDurationMinutes === null
        ? null
        : Math.round(realDurationMinutes * 100) / 100

      params.simulationSimNow.value = typeof payload.sim_now === 'string' ? payload.sim_now : null

      if (statusValue === 'completed') {
        const parsedResult = params.normalizeSimulationResult(payload.result)
        if (parsedResult) {
          params.results.value = parsedResult
        }
        params.stopLoading()
        clearSimulationPolling()
        return
      }

      if (statusValue === 'failed') {
        params.error.value = typeof payload.error === 'string'
          ? payload.error
          : 'Симуляция завершилась с ошибкой'
        params.stopLoading()
        clearSimulationPolling()
      }
    } catch (err) {
      logger.debug('[ZoneSimulationModal] Simulation status poll failed', err)
    }
  }

  const startSimulationPolling = (jobId: string): void => {
    clearSimulationPolling()
    void pollSimulationStatus(jobId)
    simulationPollTimer = setInterval(() => {
      void pollSimulationStatus(jobId)
    }, 2000)
  }

  const attachActiveSimulation = (simulationId: number, status?: string | null): void => {
    params.attachSimulation(simulationId)

    const mappedStatus = mapActiveSimulationStatus(status)
    if (mappedStatus && !params.simulationJobId.value) {
      params.simulationStatus.value = mappedStatus
    }
  }

  watch(
    () => [
      params.activeSimulationId.value,
      params.activeSimulationStatus.value,
      params.isVisible.value,
      params.loading.value,
    ] as const,
    ([activeId, activeStatus, isVisibleNow, isLoading]) => {
      if (!isVisibleNow || isLoading) return
      if (!activeId || params.simulationJobId.value) return
      attachActiveSimulation(activeId, activeStatus)
    },
    { immediate: true }
  )

  return {
    clearSimulationPolling,
    startSimulationPolling,
  }
}
