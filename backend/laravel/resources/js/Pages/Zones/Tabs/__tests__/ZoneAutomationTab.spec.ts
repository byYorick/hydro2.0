import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))

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

vi.mock('@/Components/AIPredictionsSection.vue', () => ({
  default: { name: 'AIPredictionsSection', template: '<div />' },
}))

vi.mock('@/Components/AutomationEngine.vue', () => ({
  default: { name: 'AutomationEngine', template: '<div />' },
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

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

import ZoneAutomationTab from '../ZoneAutomationTab.vue'

describe('ZoneAutomationTab.vue', () => {
  beforeEach(() => {
    window.localStorage.clear()
    roleState.role = 'agronomist'
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
})
