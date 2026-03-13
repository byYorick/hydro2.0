import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGrowthCycleWizard, type GrowthCycleWizardEmit } from '../useGrowthCycleWizard'
import type { useApi } from '../useApi'

function mountWizardHarness(options?: {
  show?: boolean
  zoneId?: number
  initialData?: Record<string, unknown> | null
}) {
  const emit = vi.fn() as unknown as GrowthCycleWizardEmit
  const api = {
    get: vi.fn().mockResolvedValue({ data: { status: 'ok', data: { recipes: [], plants: [] } } }),
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
      zoneId: options?.zoneId,
      initialData: options?.initialData ?? null,
    },
  })

  return {
    wrapper,
    wizard: (wrapper.vm as { wizard: ReturnType<typeof useGrowthCycleWizard> }).wizard,
    api,
    showToast,
  }
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

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

  it('не даёт пройти шаг калибровки без загруженных насосов и явного skip', () => {
    const { wizard } = mountWizardHarness()

    wizard.currentStep.value = 5

    expect(wizard.canProceed.value).toBe(false)
    expect(wizard.nextStepBlockedReason.value).toContain('Загрузите список насосов')
  })

  it('не восстанавливает draft сразу на confirm и сбрасывает скрытый skip', async () => {
    localStorage.setItem('growthCycleWizardDraft:zone-1', JSON.stringify({
      currentStep: 6,
      calibrationSkipped: true,
      startedAt: '2026-03-14T10:00',
      climateForm: { enabled: true },
      waterForm: { systemType: 'drip' },
      lightingForm: { enabled: false },
    }))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      status: 404,
      ok: false,
      json: vi.fn(),
    }))

    const { wizard } = mountWizardHarness({
      show: true,
      zoneId: 1,
      initialData: {
        plantId: 1,
        recipeId: 1,
        recipeRevisionId: 1,
        startedAt: '2026-03-14T10:00',
      },
    })

    await flushPromises()
    await nextTick()

    expect(wizard.currentStep.value).toBe(4)
    expect(wizard.form.value.calibrationSkipped).toBe(false)
  })

  it('перед submit пытается загрузить насосы и не стартует цикл без калибровок', async () => {
    const { wizard, api, showToast } = mountWizardHarness()

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-14T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3

    vi.mocked(api.get).mockResolvedValueOnce({ data: { status: 'ok', data: [] } })

    await wizard.onSubmit()

    expect(api.get).toHaveBeenCalledWith('/api/nodes?zone_id=7')
    expect(api.post).not.toHaveBeenCalled()
    expect(wizard.currentStep.value).toBe(5)
    expect(showToast).toHaveBeenCalledTimes(1)
    expect(showToast.mock.calls[0][0]).toContain('Заполните калибровки насосов')
  })
})
