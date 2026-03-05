import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useGrowthCycleWizard, type GrowthCycleWizardEmit } from '../useGrowthCycleWizard'
import type { useApi } from '../useApi'

function mountWizardHarness(options?: { show?: boolean }) {
  const emit = vi.fn() as unknown as GrowthCycleWizardEmit
  const api = {
    get: vi.fn(),
    post: vi.fn(),
  } as unknown as ReturnType<typeof useApi>['api']
  const showToast = vi.fn()
  const fetchZones = vi.fn()

  const Harness = defineComponent({
    props: {
      show: {
        type: Boolean,
        default: false,
      },
      zoneId: {
        type: Number,
        default: undefined,
      },
      zoneName: {
        type: String,
        default: '',
      },
      currentPhaseTargets: {
        type: Object,
        default: undefined,
      },
      activeCycle: {
        type: Object,
        default: undefined,
      },
      initialData: {
        type: Object,
        default: null,
      },
    },
    setup(props) {
      const wizard = useGrowthCycleWizard({
        props,
        emit,
        api,
        showToast,
        fetchZones,
      })

      return { wizard }
    },
    template: '<div />',
  })

  const wrapper = mount(Harness, {
    props: {
      show: options?.show ?? false,
    },
  })

  return {
    wrapper,
    wizard: (wrapper.vm as { wizard: ReturnType<typeof useGrowthCycleWizard> }).wizard,
    showToast,
  }
}

describe('useGrowthCycleWizard', () => {
  it('нормализует tanksCount и drain при переключении на drip', async () => {
    const { wizard } = mountWizardHarness()
    const waterForm = wizard.waterForm.value

    waterForm.systemType = 'substrate_trays'
    waterForm.tanksCount = 3
    waterForm.enableDrainControl = true
    await nextTick()

    waterForm.systemType = 'drip'
    await nextTick()

    expect(waterForm.tanksCount).toBe(2)
    expect(waterForm.enableDrainControl).toBe(false)
  })

  it('блокирует переход со шага автоматики при невалидных vent границах', async () => {
    const { wizard, showToast } = mountWizardHarness()
    const currentStep = wizard.currentStep
    const climateForm = wizard.climateForm.value

    currentStep.value = 4
    climateForm.ventMinPercent = 90
    climateForm.ventMaxPercent = 10

    wizard.nextStep()
    await nextTick()

    expect(currentStep.value).toBe(4)
    expect(showToast).toHaveBeenCalledTimes(1)
    expect(showToast.mock.calls[0][0]).toContain('форточек')
  })
})
