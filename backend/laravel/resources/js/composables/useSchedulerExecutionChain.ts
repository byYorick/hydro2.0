import { onMounted, onUnmounted, watch, type Ref } from 'vue'
import { subscribeToExecutionChain, type SchedulerChainSubscription } from '@/ws/schedulerChainChannel'
import type { ChainStep, ExecutionRun, ScheduleWorkspace } from '@/composables/zoneScheduleWorkspaceTypes'

export function useSchedulerExecutionChain(zoneId: () => number | null, selectedExecution: Ref<ExecutionRun | null>, workspace: Ref<ScheduleWorkspace | null>) {
  function chainStepKey(step: ChainStep): string {
    return `${step.step ?? ''}|${step.ref ?? ''}|${step.at ?? ''}`
  }

  function appendUniqueChainStep(chain: ChainStep[] | undefined, step: ChainStep): ChainStep[] {
    const current = chain ?? []
    const key = chainStepKey(step)
    if (current.some((item) => chainStepKey(item) === key)) {
      return current
    }
    return [...current, step]
  }

  function applyChainStep(executionId: string, step: ChainStep): void {
    if (selectedExecution.value?.execution_id === executionId) {
      selectedExecution.value = {
        ...selectedExecution.value,
        chain: appendUniqueChainStep(selectedExecution.value.chain, step),
      }
    }
    if (workspace.value?.execution?.active_run?.execution_id === executionId) {
      const active = workspace.value.execution.active_run
      active.chain = appendUniqueChainStep(active.chain, step)
    }
  }

  let chainSubscription: SchedulerChainSubscription | null = null

  function resubscribeChain(): void {
    chainSubscription?.unsubscribe()
    chainSubscription = null
    const subscribedZone = zoneId()
    if (subscribedZone === null || subscribedZone === undefined) return
    chainSubscription = subscribeToExecutionChain(subscribedZone, {
      onStep: (executionId, step) => { if (zoneId() === subscribedZone) applyChainStep(executionId, step) },
    })
  }

  onMounted(resubscribeChain)
  onUnmounted(() => chainSubscription?.unsubscribe())
  watch(zoneId, resubscribeChain)
}
