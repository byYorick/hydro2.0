/**
 * Навигация мастера запуска: линейный stepper + быстрый переход на доп. шаги.
 */
import type { ComputedRef, Ref } from 'vue'
import type { LaunchStep } from '@/Components/Launch/Shell/types'
import type { ProceedVerdict } from '@/composables/useLaunchSteps'
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow'

interface UseLaunchWizardNavInput {
  currentStep: Ref<string>
  stepperSteps: ComputedRef<LaunchStep[]>
  allVisibleSteps: ComputedRef<LaunchStep[]>
  activeIndex: ComputedRef<number>
  isAdvancedStep: ComputedRef<boolean>
  canProceedStep: (stepId: string) => ProceedVerdict
  readinessBlockers: ComputedRef<LaunchFlowReadinessBlocker[]>
  showToast: (message: string, type?: 'success' | 'error' | 'warning' | 'info') => void
}

export function useLaunchWizardNav(input: UseLaunchWizardNavInput) {
  function hasVisibleStep(stepId: string): boolean {
    return input.allVisibleSteps.value.some((s) => s.id === stepId)
  }

  function jumpToStep(stepId: string): void {
    if (!hasVisibleStep(stepId)) return
    input.currentStep.value = stepId
  }

  function warnIfPreviewBlocked(stepId: string): boolean {
    const firstBlocker = input.readinessBlockers.value[0]
    if (firstBlocker && stepId === 'preview') {
      input.showToast(firstBlocker.message || 'Есть активные блокеры readiness', 'warning')
      return true
    }
    return false
  }

  function onStepSelect(index: number): void {
    const step = input.stepperSteps.value[index]
    if (!step) return
    if (index <= input.activeIndex.value) {
      input.currentStep.value = step.id
      return
    }

    if (warnIfPreviewBlocked(step.id)) return

    for (let i = 0; i < index; i++) {
      if (input.canProceedStep(input.stepperSteps.value[i].id) !== true) {
        const reason = input.canProceedStep(input.stepperSteps.value[i].id) as { reason?: string }
        input.showToast(reason?.reason || 'Заполните предыдущие шаги', 'warning')
        return
      }
    }
    input.currentStep.value = step.id
  }

  function onQuickJump(index: number): void {
    const step = input.allVisibleSteps.value[index]
    if (!step) return
    if (warnIfPreviewBlocked(step.id)) return
    input.currentStep.value = step.id
  }

  function goNext(): void {
    if (input.isAdvancedStep.value) {
      input.currentStep.value = 'preview'
      return
    }

    const i = input.activeIndex.value
    const next = input.stepperSteps.value[i + 1]
    if (!next) return
    if (warnIfPreviewBlocked(next.id)) return

    const verdict = input.canProceedStep(input.currentStep.value)
    if (verdict !== true) {
      input.showToast(verdict.reason, 'warning')
      return
    }
    input.currentStep.value = next.id
  }

  function goBack(): void {
    if (input.isAdvancedStep.value) {
      input.currentStep.value = hasVisibleStep('recipe')
        ? 'recipe'
        : (input.stepperSteps.value[0]?.id ?? '')
      return
    }

    const prev = input.stepperSteps.value[input.activeIndex.value - 1]
    if (prev) input.currentStep.value = prev.id
  }

  return {
    hasVisibleStep,
    jumpToStep,
    onStepSelect,
    onQuickJump,
    goNext,
    goBack,
  }
}
