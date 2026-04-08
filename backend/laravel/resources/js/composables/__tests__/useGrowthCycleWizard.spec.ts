import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGrowthCycleWizard, type GrowthCycleWizardEmit } from '../useGrowthCycleWizard'
import type { useApi } from '../useApi'

const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())

function buildRecipeRevisionResponse(phases: Array<Record<string, unknown>> = [
  {
    id: 30,
    phase_index: 0,
    name: 'Первая фаза',
    ph_target: 5.8,
    ph_min: 5.6,
    ph_max: 6.0,
    ec_target: 1.5,
    ec_min: 1.3,
    ec_max: 1.7,
  },
]) {
  return {
    data: {
      status: 'ok',
      data: {
        id: 3,
        phases,
      },
    },
  }
}

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
  }),
}))

function authorityDocument(namespace: string, payload: Record<string, unknown>, scopeType: 'system' | 'zone' = 'zone', scopeId = 7) {
  return {
    namespace,
    scope_type: scopeType,
    scope_id: scopeId,
    schema_version: 1,
    payload,
    status: 'valid',
    updated_at: '2026-03-24T10:00:00Z',
    updated_by: 5,
  }
}

function installAuthorityMocks(zoneLogicProfilePayload?: Record<string, unknown>) {
  getDocumentMock.mockImplementation((scopeType: string, scopeId: number, namespace: string) => {
    if (namespace === 'system.automation_defaults') {
      return Promise.resolve(authorityDocument(namespace, {
        climate_enabled: true,
        climate_day_temp_c: 23,
        climate_night_temp_c: 20,
        climate_day_humidity_pct: 62,
        climate_night_humidity_pct: 70,
        climate_interval_min: 5,
        climate_day_start_hhmm: '07:00',
        climate_night_start_hhmm: '19:00',
        climate_vent_min_pct: 15,
        climate_vent_max_pct: 85,
        climate_use_external_telemetry: true,
        climate_outside_temp_min_c: 4,
        climate_outside_temp_max_c: 34,
        climate_outside_humidity_max_pct: 90,
        climate_manual_override_enabled: true,
        climate_manual_override_minutes: 30,
        water_system_type: 'drip',
        water_tanks_count: 2,
        water_clean_tank_fill_l: 300,
        water_nutrient_tank_target_l: 280,
        water_irrigation_batch_l: 20,
        water_interval_min: 30,
        water_duration_sec: 120,
        water_fill_temperature_c: 20,
        water_fill_window_start_hhmm: '05:00',
        water_fill_window_end_hhmm: '07:00',
        water_target_ph: 5.8,
        water_target_ec: 1.6,
        water_ph_pct: 5,
        water_ec_pct: 10,
        water_valve_switching_enabled: true,
        water_correction_during_irrigation: true,
        water_drain_control_enabled: false,
        water_drain_target_pct: 20,
        water_diagnostics_enabled: true,
        water_diagnostics_interval_min: 15,
        water_cycle_start_workflow_enabled: true,
        water_diagnostics_workflow: 'startup',
        water_clean_tank_full_threshold: 0.95,
        water_refill_duration_sec: 30,
        water_refill_timeout_sec: 600,
        water_startup_clean_fill_timeout_sec: 1200,
        water_startup_solution_fill_timeout_sec: 1800,
        water_startup_prepare_recirculation_timeout_sec: 1200,
        water_startup_clean_fill_retry_cycles: 1,
        water_startup_level_poll_interval_sec: 60,
        water_startup_level_switch_on_threshold: 0.5,
        water_startup_clean_max_sensor_label: 'level_clean_max',
        water_startup_solution_max_sensor_label: 'level_solution_max',
        water_irrigation_recovery_max_continue_attempts: 5,
        water_irrigation_recovery_timeout_sec: 600,
        water_irrigation_recovery_target_tolerance_ec_pct: 10,
        water_irrigation_recovery_target_tolerance_ph_pct: 5,
        water_irrigation_recovery_degraded_tolerance_ec_pct: 20,
        water_irrigation_recovery_degraded_tolerance_ph_pct: 10,
        water_irrigation_decision_strategy: 'task',
        water_irrigation_decision_lookback_sec: 1800,
        water_irrigation_decision_min_samples: 3,
        water_irrigation_decision_stale_after_sec: 600,
        water_irrigation_decision_hysteresis_pct: 2,
        water_irrigation_decision_spread_alert_threshold_pct: 12,
        water_irrigation_stop_on_solution_min: true,
        water_irrigation_auto_replay_after_setup: true,
        water_irrigation_max_setup_replays: 1,
        water_prepare_tolerance_ec_pct: 25,
        water_prepare_tolerance_ph_pct: 15,
        water_correction_max_ec_attempts: 5,
        water_correction_max_ph_attempts: 5,
        water_correction_prepare_recirculation_max_attempts: 3,
        water_correction_prepare_recirculation_max_correction_attempts: 20,
        water_correction_stabilization_sec: 60,
        water_two_tank_irrigation_start_steps: 3,
        water_two_tank_irrigation_stop_steps: 3,
        water_two_tank_clean_fill_start_steps: 1,
        water_two_tank_clean_fill_stop_steps: 1,
        water_two_tank_solution_fill_start_steps: 3,
        water_two_tank_solution_fill_stop_steps: 3,
        water_two_tank_prepare_recirculation_start_steps: 3,
        water_two_tank_prepare_recirculation_stop_steps: 3,
        water_two_tank_irrigation_recovery_start_steps: 4,
        water_two_tank_irrigation_recovery_stop_steps: 4,
        water_refill_required_node_types_csv: 'irrig',
        water_refill_preferred_channel: 'fill_valve',
        water_solution_change_enabled: false,
        water_solution_change_interval_min: 180,
        water_solution_change_duration_sec: 120,
        water_manual_irrigation_sec: 90,
        lighting_enabled: true,
        lighting_lux_day: 18000,
        lighting_lux_night: 0,
        lighting_hours_on: 16,
        lighting_interval_min: 30,
        lighting_schedule_start_hhmm: '06:00',
        lighting_schedule_end_hhmm: '22:00',
        lighting_manual_intensity_pct: 75,
        lighting_manual_duration_hours: 4,
      }, 'system', 0))
    }

    if (namespace === 'system.command_templates') {
      return Promise.resolve(authorityDocument(namespace, {
        irrigation_start: [],
        irrigation_stop: [],
        clean_fill_start: [],
        clean_fill_stop: [],
        solution_fill_start: [],
        solution_fill_stop: [],
        prepare_recirculation_start: [],
        prepare_recirculation_stop: [],
        irrigation_recovery_start: [],
        irrigation_recovery_stop: [],
      }, 'system', 0))
    }

    if (namespace === 'zone.logic_profile') {
      return Promise.resolve(authorityDocument(namespace, zoneLogicProfilePayload ?? {
        active_mode: 'setup',
        profiles: {
          setup: {
            mode: 'setup',
            is_active: true,
            subsystems: {},
            command_plans: {
              schema_version: 1,
              plans: {
                diagnostics: {
                  steps: [{ channel: 'valve_clean_fill', cmd: 'set_relay', params: { state: true } }],
                },
              },
            },
            updated_at: '2026-03-24T10:00:00Z',
          },
        },
      }, scopeType === 'zone' ? 'zone' : 'zone', scopeId))
    }

    return Promise.reject(new Error(`Unexpected authority namespace ${namespace}`))
  })

  updateDocumentMock.mockImplementation(async (_scopeType: string, scopeId: number, namespace: string, payload: Record<string, unknown>) =>
    authorityDocument(namespace, payload, 'zone', scopeId)
  )
}

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

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse())
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
  afterEach(() => {
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
  })

  it('нормализует tanksCount и drain при переключении на drip', async () => {
    installAuthorityMocks()
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
    installAuthorityMocks()
    const { wizard } = mountWizardHarness()
    const waterForm = wizard.waterForm.value

    waterForm.systemType = 'substrate_trays'
    waterForm.tanksCount = 3
    waterForm.diagnosticsWorkflow = 'startup'
    await nextTick()

    expect(waterForm.diagnosticsWorkflow).toBe('cycle_start')
  })

  it('блокирует переход со шага автоматики при невалидных vent границах', async () => {
    installAuthorityMocks()
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

  it('не блокирует шаг калибровки локальными legacy-данными', () => {
    installAuthorityMocks()
    const { wizard } = mountWizardHarness()

    wizard.currentStep.value = 5

    expect(wizard.canProceed.value).toBe(true)
    expect(wizard.nextStepBlockedReason.value).toBe('')
  })

  it('подтягивает pH/EC из первой фазы рецепта по phase_index', async () => {
    installAuthorityMocks()
    const { wizard, api } = mountWizardHarness()

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [
                {
                  id: 1,
                  name: 'Recipe A',
                  latest_published_revision_id: 3,
                },
              ],
            },
          },
        })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              id: 3,
              phases: [
                {
                  id: 31,
                  phase_index: 1,
                  name: 'Вторая фаза',
                  ph_target: 6.6,
                  ph_min: 6.4,
                  ph_max: 6.8,
                  ec_target: 1.9,
                  ec_min: 1.7,
                  ec_max: 2.1,
                },
                {
                  id: 30,
                  phase_index: 0,
                  name: 'Первая фаза',
                  ph_target: 5.8,
                  ph_min: 5.6,
                  ph_max: 6.0,
                  ec_target: 1.5,
                  ec_min: 1.3,
                  ec_max: 1.7,
                },
              ],
            },
          },
        })
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

    wizard.selectedRevisionId.value = 3
    await flushPromises()

    expect(wizard.waterForm.value.targetPh).toBe(5.8)
    expect(wizard.waterForm.value.targetEc).toBe(1.5)
  })

  it('не перетирает target pH/EC рецепта значениями zone automation profile', async () => {
    installAuthorityMocks({
      active_mode: 'setup',
      profiles: {
        setup: {
          mode: 'setup',
          is_active: true,
          subsystems: {
            diagnostics: {
              execution: {
                target_ph: 5.8,
                target_ec: 1.6,
              },
            },
          },
          command_plans: {
            schema_version: 1,
            plans: {},
          },
          updated_at: '2026-03-24T10:00:00Z',
        },
      },
    })
    const { wizard, api } = mountWizardHarness({
      show: true,
      initialData: {
        plantId: 2,
        recipeId: 1,
        recipeRevisionId: 3,
        startedAt: '2026-03-24T10:00',
      },
    })

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [
                {
                  id: 1,
                  name: 'Recipe A',
                  latest_published_revision_id: 3,
                },
              ],
            },
          },
        })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              id: 3,
              phases: [
                {
                  id: 30,
                  phase_index: 0,
                  name: 'Первая фаза',
                  ph_target: 5.0,
                  ph_min: 4.95,
                  ph_max: 5.05,
                  ec_target: 1.5,
                  ec_min: 1.3,
                  ec_max: 1.7,
                },
              ],
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    await flushPromises()

    expect(wizard.waterForm.value.targetPh).toBe(5.0)
    expect(wizard.waterForm.value.targetEc).toBe(1.5)

    wizard.form.value.zoneId = 7
    await flushPromises()

    expect(wizard.waterForm.value.targetPh).toBe(5.0)
    expect(wizard.waterForm.value.targetEc).toBe(1.5)
  })

  it('не перетирает target pH/EC рецепта draft-данными после загрузки zone automation profile', async () => {
    installAuthorityMocks({
      active_mode: 'setup',
      profiles: {
        setup: {
          mode: 'setup',
          is_active: true,
          subsystems: {
            diagnostics: {
              execution: {
                target_ph: 5.8,
                target_ec: 1.6,
              },
            },
          },
          command_plans: {
            schema_version: 1,
            plans: {},
          },
          updated_at: '2026-03-24T10:00:00Z',
        },
      },
    })

    localStorage.setItem('growthCycleWizardDraft:zone-7', JSON.stringify({
      zoneId: 7,
      plantId: 2,
      recipeId: 1,
      recipeRevisionId: 3,
      startedAt: '2026-03-24T10:00',
      climateForm: { enabled: true },
      waterForm: {
        targetPh: 5.8,
        targetEc: 1.6,
      },
      lightingForm: { enabled: false },
      currentStep: 6,
    }))

    const { wrapper, wizard, api } = mountWizardHarness({
      show: false,
      zoneId: 7,
      initialData: {
        plantId: 2,
        recipeId: 1,
        recipeRevisionId: 3,
        startedAt: '2026-03-24T10:00',
      },
    })

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [
                {
                  id: 1,
                  name: 'Recipe A',
                  latest_published_revision_id: 3,
                },
              ],
            },
          },
        })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              id: 3,
              phases: [
                {
                  id: 30,
                  phase_index: 0,
                  name: 'Первая фаза',
                  ph_target: 5.0,
                  ph_min: 4.95,
                  ph_max: 5.05,
                  ec_target: 1.5,
                  ec_min: 1.3,
                  ec_max: 1.7,
                },
              ],
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    await wrapper.setProps({ show: true })
    await flushPromises()

    expect(wizard.waterForm.value.targetPh).toBe(5.0)
    expect(wizard.waterForm.value.targetEc).toBe(1.5)

    wizard.form.value.zoneId = 7
    await flushPromises()

    expect(wizard.waterForm.value.targetPh).toBe(5.0)
    expect(wizard.waterForm.value.targetEc).toBe(1.5)
  })

  it('не включает lighting обратно при запуске цикла, если профиль зоны уже выключил свет', async () => {
    installAuthorityMocks({
      active_mode: 'setup',
      profiles: {
        setup: {
          mode: 'setup',
          is_active: true,
          subsystems: {
            lighting: {
              enabled: false,
              execution: {
                interval_sec: 1800,
                schedule: [{ start: '06:00', end: '22:00' }],
                photoperiod: { hours_on: 16, hours_off: 8 },
              },
            },
          },
          command_plans: {
            schema_version: 1,
            plans: {},
          },
          updated_at: '2026-03-24T10:00:00Z',
        },
      },
    })
    const { wizard, api } = mountWizardHarness({
      show: true,
      zoneId: 7,
      initialData: {
        plantId: 2,
        recipeId: 1,
        recipeRevisionId: 3,
        startedAt: '2026-03-24T10:00',
      },
    })

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              data: [
                {
                  id: 1,
                  name: 'Recipe A',
                  latest_published_revision_id: 3,
                },
              ],
            },
          },
        })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse([
          {
            id: 30,
            phase_index: 0,
            name: 'Первая фаза',
            ph_target: 5.8,
            ph_min: 5.6,
            ph_max: 6.0,
            ec_target: 1.5,
            ec_min: 1.3,
            ec_max: 1.7,
            lighting_photoperiod_hours: 16,
            lighting_start_time: '06:00',
          },
        ]))
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
      if (url === '/api/zones/7/grow-cycles') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    await flushPromises()
    await nextTick()

    expect(wizard.lightingForm.value.enabled).toBe(false)

    wizard.currentStep.value = 6
    await wizard.onSubmit()

    const automationPayload = updateDocumentMock.mock.calls.find(([, scopeId, namespace]) => scopeId === 7 && namespace === 'zone.logic_profile')?.[3]
    expect(automationPayload?.profiles?.setup?.subsystems?.lighting?.enabled).toBe(false)
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.objectContaining({
      start_immediately: true,
      recipe_revision_id: 3,
      plant_id: 2,
    }))
  })

  it('не восстанавливает draft сразу на submit-шаг', async () => {
    installAuthorityMocks()
    localStorage.setItem('growthCycleWizardDraft:zone-1', JSON.stringify({
      currentStep: 6,
      startedAt: '2026-03-14T10:00',
      climateForm: { enabled: true },
      waterForm: { systemType: 'drip' },
      lightingForm: { enabled: false },
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

    expect(wizard.currentStep.value).toBe(5)
  })

  it('не запускает цикл, если readiness сообщает об отсутствующих pump calibration', async () => {
    installAuthorityMocks()
    const { wizard, api, showToast } = mountWizardHarness()

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-14T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3
    await flushPromises()

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse())
      }

      if (url === '/api/zones/7/health') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              readiness: {
                ready: false,
                errors: ['Required pump calibrations are missing: ec_npk_pump'],
              },
            },
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    await wizard.onSubmit()

    expect(api.post).not.toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.anything())
    expect(api.post).not.toHaveBeenCalledWith('/api/zones/7/calibrate-pump', expect.anything())
    expect(wizard.error.value).toContain('Required pump calibrations are missing')
    expect(showToast).toHaveBeenCalledWith(
      'Required pump calibrations are missing: ec_npk_pump',
      'error',
      expect.any(Number),
    )
  })

  it('не запускает цикл, если readiness сообщает о несохранённых PID-конфигах', async () => {
    installAuthorityMocks()
    const { wizard, api, showToast } = mountWizardHarness()

    wizard.currentStep.value = 6
    wizard.form.value.zoneId = 7
    wizard.form.value.startedAt = '2026-03-14T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3
    await flushPromises()

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

  it('сохраняет automation profile и запускает цикл без legacy pump calibration submit-а', async () => {
    installAuthorityMocks()
    const { wizard, api, showToast } = mountWizardHarness()
    const callOrder: string[] = []

    wizard.form.value.zoneId = 7
    await nextTick()
    wizard.form.value.startedAt = '2026-03-24T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3

    vi.mocked(api.get).mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse())
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

    updateDocumentMock.mockImplementation(async (_scopeType: string, scopeId: number, namespace: string, payload: Record<string, unknown>) => {
      callOrder.push('automation-profile')
      return authorityDocument(namespace, payload, 'zone', scopeId)
    })
    vi.mocked(api.post).mockImplementation((url: string) => {
      if (url === '/api/zones/7/grow-cycles') {
        callOrder.push('grow-cycle')
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    wizard.currentStep.value = 6
    wizard.waterForm.value.targetPh = 6.4
    wizard.waterForm.value.targetEc = 1.5
    await flushPromises()

    await wizard.onSubmit()

    const automationIndex = callOrder.indexOf('automation-profile')
    const finalReadinessIndex = callOrder.lastIndexOf('readiness')
    const growCycleIndex = callOrder.indexOf('grow-cycle')

    expect(automationIndex).toBeGreaterThanOrEqual(0)
    expect(finalReadinessIndex).toBeGreaterThan(automationIndex)
    expect(growCycleIndex).toBeGreaterThan(finalReadinessIndex)
    expect(updateDocumentMock).toHaveBeenCalledWith('zone', 7, 'zone.logic_profile', expect.any(Object))
    const automationPayload = updateDocumentMock.mock.calls.find(([, scopeId, namespace]) => scopeId === 7 && namespace === 'zone.logic_profile')?.[3]
    expect(automationPayload?.profiles?.setup?.command_plans?.schema_version).toBe(1)
    expect(automationPayload?.profiles?.setup?.command_plans?.plans?.diagnostics?.steps).toHaveLength(1)
    expect(automationPayload?.profiles?.setup?.subsystems?.irrigation?.execution?.interval_minutes).toBeGreaterThan(0)
    expect(automationPayload?.profiles?.setup?.subsystems?.irrigation?.execution?.duration_seconds).toBeGreaterThan(0)
    expect(automationPayload?.profiles?.setup?.subsystems?.irrigation?.decision?.strategy).toBe('task')
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining('/calibrate-pump'), expect.anything())
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.objectContaining({
      start_immediately: true,
      recipe_revision_id: 3,
      plant_id: 2,
    }))
    const growCyclePayload = vi.mocked(api.post).mock.calls.find(([url]) => url === '/api/zones/7/grow-cycles')?.[1] as Record<string, unknown> | undefined
    expect(growCyclePayload?.phase_overrides).toBeUndefined()
    expect(showToast).toHaveBeenCalledWith(
      'Цикл выращивания успешно запущен',
      'success',
      expect.any(Number),
    )
  })

  it('сохраняет smart irrigation настройки в automation profile', async () => {
    installAuthorityMocks()
    const { wizard, api } = mountWizardHarness()

    wizard.form.value.zoneId = 7
    await nextTick()
    wizard.form.value.startedAt = '2026-03-24T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3
    wizard.waterForm.value.irrigationDecisionStrategy = 'smart_soil_v1'
    wizard.waterForm.value.intervalMinutes = 45
    wizard.waterForm.value.durationSeconds = 180
    wizard.waterForm.value.irrigationDecisionLookbackSeconds = 2400
    wizard.waterForm.value.irrigationDecisionMinSamples = 5
    wizard.waterForm.value.irrigationDecisionStaleAfterSeconds = 900
    wizard.waterForm.value.irrigationDecisionHysteresisPct = 4.5
    wizard.waterForm.value.irrigationDecisionSpreadAlertThresholdPct = 16

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse())
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
      if (url === '/api/zones/7/grow-cycles') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    wizard.currentStep.value = 6
    await flushPromises()

    await wizard.onSubmit()

    const automationPayload = updateDocumentMock.mock.calls.find(([, scopeId, namespace]) => scopeId === 7 && namespace === 'zone.logic_profile')?.[3]
    const irrigation = automationPayload?.profiles?.setup?.subsystems?.irrigation

    expect(irrigation?.decision?.strategy).toBe('smart_soil_v1')
    expect(irrigation?.decision?.config?.lookback_sec).toBe(2400)
    expect(irrigation?.decision?.config?.min_samples).toBe(5)
    expect(irrigation?.decision?.config?.stale_after_sec).toBe(900)
    expect(irrigation?.decision?.config?.hysteresis_pct).toBe(4.5)
    expect(irrigation?.decision?.config?.spread_alert_threshold_pct).toBe(16)
    expect(irrigation?.execution?.interval_minutes).toBe(45)
    expect(irrigation?.execution?.duration_seconds).toBe(180)
  })

  it('на submit не делает запросов к legacy calibrate-pump endpoint', async () => {
    installAuthorityMocks()
    const { wizard, api } = mountWizardHarness()

    wizard.form.value.zoneId = 7
    await nextTick()
    wizard.form.value.startedAt = '2026-03-24T10:00'
    wizard.selectedPlantId.value = 2
    wizard.selectedRevisionId.value = 3

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { data: [] } } })
      }

      if (url === '/recipe-revisions/3') {
        return Promise.resolve(buildRecipeRevisionResponse())
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
      if (url === '/api/zones/7/grow-cycles') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 77 } } })
      }

      return Promise.resolve({ data: { status: 'ok' } })
    })

    wizard.currentStep.value = 6
    await flushPromises()

    await wizard.onSubmit()

    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining('/calibrate-pump'), expect.anything())
    expect(api.post).toHaveBeenCalledWith('/api/zones/7/grow-cycles', expect.any(Object))
  })

  it('загружает все страницы рецептов для визарда', async () => {
    installAuthorityMocks()
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
    installAuthorityMocks()
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
