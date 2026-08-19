import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { useLaunchWizardNav } from '../useLaunchWizardNav'
import type { LaunchStep } from '@/Components/Launch/Shell/types'
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow'

describe('useLaunchWizardNav', () => {
  it('goNext from an advanced step jumps to preview without gating', () => {
    const currentStep = ref('calibration')
    const showToast = vi.fn()
    const { goNext } = useLaunchWizardNav({
      currentStep,
      stepperSteps: computed<LaunchStep[]>(() => [
        { id: 'recipe', label: 'Рецепт', sub: '' },
        { id: 'preview', label: 'Подтверждение', sub: '' },
      ]),
      allVisibleSteps: computed<LaunchStep[]>(() => [
        { id: 'recipe', label: 'Рецепт', sub: '' },
        { id: 'calibration', label: 'Калибровка', sub: '' },
        { id: 'preview', label: 'Подтверждение', sub: '' },
      ]),
      activeIndex: computed(() => -1),
      isAdvancedStep: computed(() => true),
      canProceedStep: () => ({ ok: false, reason: 'should not matter' }),
      readinessBlockers: computed<LaunchFlowReadinessBlocker[]>(() => []),
      showToast,
    })

    goNext()
    expect(currentStep.value).toBe('preview')
    expect(showToast).not.toHaveBeenCalled()
  })

  it('goBack from an advanced step returns to recipe', () => {
    const currentStep = ref('automation')
    const { goBack } = useLaunchWizardNav({
      currentStep,
      stepperSteps: computed<LaunchStep[]>(() => [
        { id: 'recipe', label: 'Рецепт', sub: '' },
        { id: 'preview', label: 'Подтверждение', sub: '' },
      ]),
      allVisibleSteps: computed<LaunchStep[]>(() => [
        { id: 'recipe', label: 'Рецепт', sub: '' },
        { id: 'automation', label: 'Автоматика', sub: '' },
        { id: 'preview', label: 'Подтверждение', sub: '' },
      ]),
      activeIndex: computed(() => -1),
      isAdvancedStep: computed(() => true),
      canProceedStep: () => true,
      readinessBlockers: computed<LaunchFlowReadinessBlocker[]>(() => []),
      showToast: vi.fn(),
    })

    goBack()
    expect(currentStep.value).toBe('recipe')
  })
})
