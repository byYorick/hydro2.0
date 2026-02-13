import { watch, type Ref } from 'vue'
import type { SimulationInitialState } from '@/composables/useSimulationSubmit'

interface InitialTelemetry {
  ph?: number | null
  ec?: number | null
  temperature?: number | null
  humidity?: number | null
}

interface UseSimulationInitialTelemetryParams {
  initialTelemetry: Ref<InitialTelemetry | null | undefined>
  initialState: SimulationInitialState
  applyAutoDrift: () => void
}

export function useSimulationInitialTelemetry(params: UseSimulationInitialTelemetryParams) {
  const applyInitialTelemetry = (telemetry: InitialTelemetry | null | undefined): void => {
    if (!telemetry) return
    if (params.initialState.ph === null && telemetry.ph != null) {
      params.initialState.ph = telemetry.ph
    }
    if (params.initialState.ec === null && telemetry.ec != null) {
      params.initialState.ec = telemetry.ec
    }
    if (params.initialState.temp_air === null && telemetry.temperature != null) {
      params.initialState.temp_air = telemetry.temperature
    }
    if (params.initialState.humidity_air === null && telemetry.humidity != null) {
      params.initialState.humidity_air = telemetry.humidity
    }
    params.applyAutoDrift()
  }

  watch(
    () => params.initialTelemetry.value,
    (telemetry) => {
      applyInitialTelemetry(telemetry)
    },
    { immediate: true }
  )

  watch(
    () => params.initialState,
    () => {
      params.applyAutoDrift()
    },
    { deep: true }
  )
}
