import type { Ref } from 'vue'

interface UseSimulationRuntimeStateParams<SimulationReport, SimulationAction, SimulationPidStatus> {
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
}

export function useSimulationRuntimeState<SimulationReport, SimulationAction, SimulationPidStatus>(
  params: UseSimulationRuntimeStateParams<SimulationReport, SimulationAction, SimulationPidStatus>
) {
  const resetSimulationRuntimeState = (): void => {
    params.simulationProgressValue.value = null
    params.simulationElapsedMinutes.value = null
    params.simulationRealDurationMinutes.value = null
    params.simulationSimNow.value = null
    params.simulationEngine.value = null
    params.simulationMode.value = null
    params.simulationProgressSource.value = null
    params.simulationActions.value = []
    params.simulationPidStatuses.value = []
    params.simulationCurrentPhase.value = null
    params.simulationReport.value = null
  }

  return {
    resetSimulationRuntimeState,
  }
}
