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
    get: vi.fn().mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    }),
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
    waterForm.diagnosticsWorkflow = 'cycle_start'
    await nextTick()

    waterForm.systemType = 'drip'
    await nextTick()

    expect(waterForm.tanksCount).toBe(2)
    expect(waterForm.enableDrainControl).toBe(false)
    expect(waterForm.diagnosticsWorkflow).toBe('startup')
  })

  it('нормализует diagnosticsWorkflow при смене топологии на 3 бака', async () => {
    const { wizard } = mountWizardHarness()
    const waterForm = wizard.waterForm.value

    waterForm.systemType = 'substrate_trays'
    waterForm.tanksCount = 3
    waterForm.diagnosticsWorkflow = 'startup'
    await nextTick()

    expect(waterForm.diagnosticsWorkflow).toBe('cycle_start')
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

  it('не запускает цикл, если readiness сообщает о несохранённых PID-конфигах', async () => {
    const { wizard, api, showToast } = mountWizardHarness()

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-14T10:00'
    wizard.form.value.calibrationSkipped = true
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/api/zones/7/health') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              readiness: {
                ready: false,
                errors: ['PID-настройки pH не сохранены для зоны'],
              },
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    await wizard.onSubmit()

    expect(api.post).not.toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.anything())
    expect(wizard.error.value).toContain('PID-настройки pH')
    expect(wizard.errorDetails.value).toContain('PID-настройки pH не сохранены для зоны')
    expect(showToast).toHaveBeenCalledWith(
      'PID-настройки pH не сохранены для зоны',
      'error',
      expect.any(Number),
    )
  })

  it('сохраняет automation profile и калибровки до старта цикла', async () => {
    const { wizard, api, showToast } = mountWizardHarness()
    const callOrder: string[] = []

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-24T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3
    wizard.zoneChannelsLoaded.value = true
    wizard.form.value.calibrations = [{
      node_channel_id: 101,
      component: 'ph_down',
      channel_label: 'pH Down',
      ml_per_sec: 1.2,
      skip: false,
    }]

    vi.mocked(api.get).mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/api/zones/7/health') {
        callOrder.push('readiness')
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              readiness: {
                ready: true,
                errors: [],
              },
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] }, config })
    })

    vi.mocked(api.post).mockImplementation((url: string) => {
      if (url === '/api/zones/7/automation-logic-profile') {
        callOrder.push('automation-profile')
        return Promise.resolve({ data: { status: 'ok' } })
      }

      if (url === '/api/zones/7/calibrate-pump') {
        callOrder.push('pump-calibration')
        return Promise.resolve({ data: { status: 'ok' } })
      }

      if (url === '/api/zones/7/grow-cycles') {
        callOrder.push('grow-cycle')
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    await wizard.onSubmit()

    const automationIndex = callOrder.indexOf('automation-profile')
    const calibrationIndex = callOrder.indexOf('pump-calibration')
    const finalReadinessIndex = callOrder.lastIndexOf('readiness')
    const growCycleIndex = callOrder.indexOf('grow-cycle')

    expect(automationIndex).toBeGreaterThanOrEqual(0)
    expect(calibrationIndex).toBeGreaterThan(automationIndex)
    expect(finalReadinessIndex).toBeGreaterThan(calibrationIndex)
    expect(growCycleIndex).toBeGreaterThan(finalReadinessIndex)
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/automation-logic-profile', expect.any(Object))
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/calibrate-pump', expect.objectContaining({
      node_channel_id: 101,
      manual_override: true,
      skip_run: true,
    }))
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.objectContaining({
      start_immediately: true,
      recipe_revision_id: 3,
      plant_id: 2,
    }))
    expect(showToast).toHaveBeenCalledWith(
      'Цикл выращивания успешно запущен',
      'success',
      expect.any(Number),
    )
  })

  it('не стартует цикл, если сохранение калибровок завершилось ошибкой', async () => {
    const { wizard, api, showToast } = mountWizardHarness()

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-24T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3
    wizard.zoneChannelsLoaded.value = true
    wizard.form.value.calibrations = [{
      node_channel_id: 101,
      component: 'ph_down',
      channel_label: 'pH Down',
      ml_per_sec: 1.2,
      skip: false,
    }]

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/api/zones/7/health') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              readiness: {
                ready: true,
                errors: [],
              },
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    vi.mocked(api.post).mockImplementation((url: string) => {
      if (url === '/api/zones/7/automation-logic-profile') {
        return Promise.resolve({ data: { status: 'ok' } })
      }

      if (url === '/api/zones/7/calibrate-pump') {
        return Promise.reject(new Error('save calibration failed'))
      }

      if (url === '/api/zones/7/grow-cycles') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    await wizard.onSubmit()

    expect(api.post).not.toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.anything())
    expect(wizard.error.value).toContain('Не удалось сохранить калибровки насосов')
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining('Не удалось сохранить калибровки насосов'),
      'error',
      expect.any(Number),
    )
  })

  it('загружает все страницы рецептов для визарда', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      status: 404,
      ok: false,
      json: vi.fn(),
    }))

    const { wrapper, wizard, api } = mountWizardHarness({
      show: false,
      zoneId: 1,
    })

    vi.mocked(api.get).mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes' && config?.params?.page === 1) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [{
                id: 10,
                name: 'Recipe 10',
                latest_published_revision_id: 110,
              }],
              current_page: 1,
              last_page: 2,
            },
          },
        })
      }

      if (url === '/recipes' && config?.params?.page === 2) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [{
                id: 11,
                name: 'Recipe 11',
                latest_published_revision_id: 111,
              }],
              current_page: 2,
              last_page: 2,
            },
          },
        })
      }

      if (url === '/api/zones/1/health') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              readiness: {
                ready: false,
                errors: [],
              },
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    await wrapper.setProps({ show: true })
    await flushPromises()
    await nextTick()

    expect(wizard.availableRecipes.value.map((recipe) => recipe.id)).toEqual([10, 11])
    expect(api.get).toHaveBeenCalledWith('/recipes', { params: { per_page: 100, page: 1 } })
    expect(api.get).toHaveBeenCalledWith('/recipes', { params: { per_page: 100, page: 2 } })
  })

  it('берет system_type из recipe phase и не подменяет drip на substrate_trays', async () => {
    const { wizard, api } = mountWizardHarness()

    wizard.selectedRecipe.value = {
      id: 10,
      latest_published_revision_id: 55,
    } as any

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/recipe-revisions/55') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              id: 55,
              phases: [{
                irrigation_mode: 'SUBSTRATE',
                extensions: {
                  subsystems: {
                    irrigation: {
                      targets: {
                        system_type: 'drip',
                      },
                    },
                  },
                },
              }],
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    wizard.selectedRevisionId.value = 55
    await flushPromises()
    await nextTick()

    expect(wizard.waterForm.value.systemType).toBe('drip')
  })
})
