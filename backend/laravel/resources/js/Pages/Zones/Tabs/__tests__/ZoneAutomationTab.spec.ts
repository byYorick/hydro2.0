import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))
const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: {
          role: roleState.role,
        },
      },
    },
  }),
}))

vi.mock('@/composables/useSensorCalibrationSettings', () => ({
  useSensorCalibrationSettings: () => ({
    value: {
      ph_point_1_value: 7,
      ph_point_2_value: 4.01,
      ec_point_1_tds: 1413,
      ec_point_2_tds: 707,
      reminder_days: 30,
      critical_days: 90,
      command_timeout_sec: 10,
      ph_reference_min: 1,
      ph_reference_max: 12,
      ec_tds_reference_max: 10000,
    },
  }),
}))

vi.mock('@/Components/AIPredictionsSection.vue', () => ({
  default: { name: 'AIPredictionsSection', template: '<div />' },
}))

vi.mock('@/Components/CorrectionRuntimeReadinessCard.vue', () => ({
  default: {
    name: 'CorrectionRuntimeReadinessCard',
    emits: ['focus-process-calibration', 'open-pump-calibration'],
    template: '<div><button data-testid="mock-open-pump" @click="$emit(\'open-pump-calibration\')" /></div>',
  },
}))

vi.mock('@/Components/ProcessCalibrationPanel.vue', () => ({
  default: { name: 'ProcessCalibrationPanel', template: '<div />' },
}))

vi.mock('@/Components/ZoneAutomationAccordionSection.vue', () => ({
  default: {
    name: 'ZoneAutomationAccordionSection',
    props: ['title', 'defaultOpen'],
    template: `
      <section>
        <div>{{ title }}<slot name="badge" /></div>
        <div><slot /></div>
      </section>
    `,
  },
}))

vi.mock('@/Components/PumpCalibrationsPanel.vue', () => ({
  default: {
    name: 'PumpCalibrationsPanel',
    props: ['saveSuccessSeq', 'runSuccessSeq'],
    emits: ['open-pump-calibration'],
    template: `
      <div>
        <span data-testid="mock-pump-save-seq">{{ saveSuccessSeq }}</span>
        <span data-testid="mock-pump-run-seq">{{ runSuccessSeq }}</span>
        <button data-testid="mock-open-pump-panel" @click="$emit('open-pump-calibration')" />
      </div>
    `,
  },
}))

vi.mock('@/Components/SensorCalibrationStatus.vue', () => ({
  default: { name: 'SensorCalibrationStatus', template: '<div />' },
}))

vi.mock('@/Components/RelayAutotuneTrigger.vue', () => ({
  default: { name: 'RelayAutotuneTrigger', template: '<div />' },
}))

vi.mock('@/Components/ZonePumpCalibrationSettingsCard.vue', () => ({
  default: { name: 'ZonePumpCalibrationSettingsCard', template: '<div />' },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'size', 'variant'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/composables/useCommands', () => ({
  useCommands: () => ({
    sendZoneCommand: vi.fn().mockResolvedValue({ status: 'ok' }),
  }),
}))

async function unwrapEnvelope(rawPromise: Promise<unknown>): Promise<unknown> {
  const raw = await rawPromise
  if (raw && typeof raw === 'object' && 'data' in (raw as Record<string, unknown>)) {
    return (raw as { data: unknown }).data
  }
  return raw
}

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getControlMode: (zoneId: number) =>
        unwrapEnvelope(apiGetMock(`/api/zones/${zoneId}/control-mode`)),
      setControlMode: (zoneId: number, payload: Record<string, unknown>) =>
        unwrapEnvelope(apiPostMock(`/api/zones/${zoneId}/control-mode`, payload)),
      runManualStep: (zoneId: number, payload: Record<string, unknown>) =>
        apiPostMock(`/api/zones/${zoneId}/manual-step`, payload),
      getState: (zoneId: number) => unwrapEnvelope(apiGetMock(`/api/zones/${zoneId}/state`)),
    },
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

import ZoneAutomationTab from '../ZoneAutomationTab.vue'

function defaultStateResponse(zoneId = 42) {
  return {
    data: {
      zone_id: zoneId,
      state: 'TANK_FILLING',
      state_label: 'Набор бака с раствором',
      state_details: {
        started_at: '2026-02-10T08:00:00Z',
        elapsed_sec: 45,
        progress_percent: 30,
        failed: false,
      },
      system_config: {
        tanks_count: 2,
        system_type: 'drip',
        clean_tank_capacity_l: 300,
        nutrient_tank_capacity_l: 280,
      },
      current_levels: {
        clean_tank_level_percent: 95,
        nutrient_tank_level_percent: 25,
        ph: 5.8,
        ec: 1.6,
      },
      active_processes: {
        pump_in: true,
        circulation_pump: false,
        ph_correction: false,
        ec_correction: false,
      },
      timeline: [],
      next_state: 'TANK_RECIRC',
      estimated_completion_sec: 120,
      control_mode: 'auto',
      allowed_manual_steps: [
        'clean_fill_start',
        'clean_fill_stop',
        'solution_fill_start',
        'solution_fill_stop',
      ],
      state_meta: {
        source: 'live',
        is_stale: false,
        served_at: '2026-02-10T08:00:30Z',
      },
    },
  }
}

describe('ZoneAutomationTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    roleState.role = 'agronomist'
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    apiPostMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          active_mode: 'working',
          profiles: {
            working: {
              mode: 'working',
              is_active: true,
              subsystems: {},
              updated_at: '2026-02-10T08:00:00Z',
            },
          },
        },
      },
    })
    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/automation-logic-profile')) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              active_mode: 'working',
              profiles: {
                working: {
                  mode: 'working',
                  is_active: true,
                  subsystems: {},
                  updated_at: '2026-02-10T08:00:00Z',
                },
              },
            },
          },
        })
      }

      if (url.includes('/state')) {
        const zoneId = Number(url.match(/\/api\/zones\/(\d+)\/state/)?.[1] ?? 42)
        return Promise.resolve(defaultStateResponse(zoneId))
      }

      return Promise.resolve({
        data: {
          status: 'ok',
          data: {
            control_mode: 'auto',
            allowed_manual_steps: ['clean_fill_start', 'solution_fill_start'],
          },
        },
      })
    })
  })

  it('подтягивает параметры автоматики из активного рецепта', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        telemetry: { temperature: 24, humidity: 58 } as any,
        targets: {
          ph: { min: 5.6, max: 6.0, target: 5.9 },
          ec: { min: 1.4, max: 1.8, target: 1.7 },
          irrigation: { interval_sec: 1800, duration_sec: 90 },
          climate_request: { temp_air_target: 25, humidity_target: 64 },
          lighting: { photoperiod_hours: 15, start_time: '05:30:00' },
          extensions: {
            subsystems: {
              irrigation: {
                targets: {
                  system_type: 'nft',
                  tanks_count: 3,
                  drain_control: { enabled: true, target_percent: 28 },
                },
              },
              climate: {
                targets: {
                  temperature: { day: 25, night: 20 },
                  humidity: { day: 60, night: 72 },
                  vent_control: { min_open_percent: 10, max_open_percent: 80 },
                },
              },
              lighting: {
                targets: {
                  lux: { day: 22000, night: 500 },
                  photoperiod: { hours_on: 15 },
                  schedule: [{ start: '05:30', end: '20:30' }],
                },
              },
            },
          },
        } as any,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.waterForm.targetPh).toBeCloseTo(5.9, 2)
    expect(vm.waterForm.targetEc).toBeCloseTo(1.7, 2)
    expect(vm.waterForm.intervalMinutes).toBe(30)
    expect(vm.waterForm.durationSeconds).toBe(90)
    expect(vm.waterForm.systemType).toBe('nft')
    expect(vm.waterForm.tanksCount).toBe(3)
    expect(vm.waterForm.enableDrainControl).toBe(true)
    expect(vm.waterForm.drainTargetPercent).toBe(28)
    expect(vm.climateForm.dayTemp).toBe(25)
    expect(vm.climateForm.nightTemp).toBe(20)
    expect(vm.climateForm.dayHumidity).toBe(60)
    expect(vm.climateForm.nightHumidity).toBe(72)
    expect(vm.climateForm.ventMinPercent).toBe(10)
    expect(vm.climateForm.ventMaxPercent).toBe(80)
    expect(vm.lightingForm.hoursOn).toBe(15)
    expect(vm.lightingForm.luxDay).toBe(22000)
    expect(vm.lightingForm.luxNight).toBe(500)
    expect(vm.lightingForm.scheduleStart).toBe('05:30')
    expect(vm.lightingForm.scheduleEnd).toBe('20:30')
    expect(wrapper.text()).toContain('pH ±0.29 (5%)')
    expect(wrapper.text()).not.toContain('Задачи автоматики')
  })

  it('пересинхронизируется при обновлении targets', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()
    await wrapper.setProps({
      targets: {
        ph: { target: 6.2 },
        ec: { target: 2.1 },
        irrigation: { interval_sec: 3600, duration_sec: 150 },
      } as any,
    })
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.waterForm.targetPh).toBeCloseTo(6.2, 2)
    expect(vm.waterForm.targetEc).toBeCloseTo(2.1, 2)
    expect(vm.waterForm.intervalMinutes).toBe(60)
    expect(vm.waterForm.durationSeconds).toBe(150)
  })

  it('безопасно форматирует телеметрию из строковых значений', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        telemetry: { temperature: '24.4', humidity: '58' } as any,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    expect((wrapper.vm as any).telemetryLabel).toBe('24.4°C / 58%')
  })

  it('блокирует изменение system_type при активном цикле', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        activeGrowCycle: { status: 'RUNNING' } as any,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    expect((wrapper.vm as any).isSystemTypeLocked).toBe(true)
    expect(wrapper.text()).toContain('Тип системы зафиксирован для активного цикла.')
  })

  it('не применяет изменения мастера до сохранения', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.climateForm.dayTemp).toBe(23)

    const editButton = wrapper.findAll('button').find((btn) => btn.text().includes('Редактировать'))
    expect(editButton).toBeTruthy()
    await editButton!.trigger('click')
    await flushPromises()

    const dayTempInput = wrapper.find('input[type="number"]')
    expect(dayTempInput.exists()).toBe(true)
    await dayTempInput.setValue('30')
    await flushPromises()
    expect(vm.climateForm.dayTemp).toBe(23)

    const wizard = wrapper.findComponent({ name: 'ZoneAutomationEditWizard' })
    wizard.vm.$emit('close')
    await flushPromises()
    expect(vm.climateForm.dayTemp).toBe(23)

    wizard.vm.$emit('apply', {
      climateForm: { ...vm.climateForm, dayTemp: 30 },
      waterForm: { ...vm.waterForm },
      lightingForm: { ...vm.lightingForm },
      zoneClimateForm: { ...vm.zoneClimateForm },
    })
    await flushPromises()

    expect(vm.climateForm.dayTemp).toBe(30)
  })

  it('санитизирует поврежденный профиль из localStorage', async () => {
    window.localStorage.setItem(
      'zone:42:automation-profile:v3',
      JSON.stringify({
        climate: { dayTemp: 'oops', dayStart: '99:99', ventMinPercent: -500 },
        water: { targetPh: 'broken', targetEc: null, intervalMinutes: 'abc', fillWindowStart: '31:99' },
        lighting: { hoursOn: 'nan', manualIntensity: 9999, scheduleStart: '26:88' },
        lastAppliedAt: 'not-a-date',
      })
    )

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {} as any,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    expect(typeof vm.waterForm.targetPh).toBe('number')
    expect(typeof vm.waterForm.targetEc).toBe('number')
    expect(vm.waterForm.targetPh).toBeCloseTo(5.8, 2)
    expect(vm.waterForm.targetEc).toBeCloseTo(1.6, 2)
    expect(vm.climateForm.dayStart).toBe('07:00')
    expect(vm.lightingForm.scheduleStart).toBe('06:00')
    expect(vm.lastAppliedAt).toBe(null)
  })

  it('перезагружает persisted-профиль при смене zoneId', async () => {
    window.localStorage.setItem(
      'zone:1:automation-profile:v3',
      JSON.stringify({
        climate: { dayTemp: 24 },
      })
    )
    window.localStorage.setItem(
      'zone:2:automation-profile:v3',
      JSON.stringify({
        climate: { dayTemp: 31 },
      })
    )

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 1,
        targets: {} as any,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.climateForm.dayTemp).toBe(24)

    await wrapper.setProps({
      zoneId: 2,
      targets: {} as any,
    })
    await flushPromises()

    expect(vm.climateForm.dayTemp).toBe(31)
  })

  it('не применяет targets предыдущей зоны при смене zoneId до обновления props', async () => {
    window.localStorage.setItem(
      'zone:2:automation-profile:v3',
      JSON.stringify({
        climate: { dayTemp: 19 },
      })
    )

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 1,
        targets: {
          extensions: {
            subsystems: {
              climate: {
                targets: {
                  temperature: { day: 30 },
                },
              },
            },
          },
        } as any,
      },
    })

    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.climateForm.dayTemp).toBe(30)

    await wrapper.setProps({ zoneId: 2 })
    await flushPromises()

    expect(vm.climateForm.dayTemp).toBe(19)
  })

  it('разрешает операционные команды для роли engineer', async () => {
    roleState.role = 'engineer'

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    const manualIrrigationButton = wrapper.findAll('button').find((btn) => btn.text() === 'Запустить полив')
    expect(manualIrrigationButton).toBeTruthy()
    expect(manualIrrigationButton!.attributes('disabled')).toBeUndefined()

    const editButton = wrapper.findAll('button').find((btn) => btn.text().includes('Редактировать'))
    expect(editButton).toBeUndefined()
  })

  it('блокирует ручное управление двухбаковой схемой для не-operator роли', async () => {
    roleState.role = 'engineer'

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    const modeSelect = wrapper.find('select.input-select')
    expect(modeSelect.exists()).toBe(true)
    expect(modeSelect.attributes('disabled')).toBeDefined()

    const manualStepButton = wrapper.findAll('button').find((btn) => btn.text() === 'Набрать чистую воду')
    expect(manualStepButton).toBeTruthy()
    expect(manualStepButton!.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('Старт рециркуляции полива')
  })

  it('пробрасывает запрос на открытие pump calibration modal', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()
    await wrapper.find('[data-testid="mock-open-pump"]').trigger('click')

    expect(wrapper.emitted('open-pump-calibration')).toBeTruthy()
  })

  it('пробрасывает запрос на открытие pump calibration modal из панели насосов', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()
    await wrapper.find('[data-testid="mock-open-pump-panel"]').trigger('click')

    expect(wrapper.emitted('open-pump-calibration')).toBeTruthy()
  })

  it('пробрасывает seq-счётчики pump calibration в стек калибровки', async () => {
    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        pumpCalibrationSaveSeq: 3,
        pumpCalibrationRunSeq: 5,
        targets: {
          ph: { target: 5.8 },
          ec: { target: 1.5 },
        } as any,
      },
    })

    await flushPromises()

    expect(wrapper.get('[data-testid="mock-pump-save-seq"]').text()).toBe('3')
    expect(wrapper.get('[data-testid="mock-pump-run-seq"]').text()).toBe('5')
  })

})
