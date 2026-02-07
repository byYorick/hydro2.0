import { onUnmounted, watch, type Ref } from 'vue'

interface UseSimulationLifecycleParams {
  isVisible: Ref<boolean>
  handleOpen: () => Promise<void> | void
  resetDriftValues: () => void
  clearSimulationPolling: () => void
  resetSimulationRuntimeState: () => void
  resetSimulationEvents: () => void
}

export function useSimulationLifecycle(params: UseSimulationLifecycleParams) {
  const resetSimulationLifecycleState = (): void => {
    params.clearSimulationPolling()
    params.resetSimulationRuntimeState()
    params.resetSimulationEvents()
  }

  watch(params.isVisible, (isOpen) => {
    if (isOpen) {
      void params.handleOpen()
      params.resetDriftValues()
      return
    }

    resetSimulationLifecycleState()
  })

  onUnmounted(() => {
    resetSimulationLifecycleState()
  })

  return {
    resetSimulationLifecycleState,
  }
}
