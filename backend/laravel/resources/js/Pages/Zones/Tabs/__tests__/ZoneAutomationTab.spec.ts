import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))
const apiGetMock = vi.hoisted(() => vi.fn())

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

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    get: apiGetMock,
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
    apiGetMock.mockReset()
    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/scheduler-tasks/')) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              task_id: 'st-test',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'completed',
              created_at: '2026-02-10T08:00:00Z',
              updated_at: '2026-02-10T08:01:00Z',
              scheduled_for: '2026-02-10T08:00:00Z',
              due_at: '2026-02-10T08:02:00Z',
              expires_at: '2026-02-10T08:05:00Z',
              correlation_id: null,
              decision: 'execute',
              reason_code: 'tank_refill_started',
              error_code: null,
              command_submitted: true,
              command_effect_confirmed: true,
              commands_total: 1,
              commands_effect_confirmed: 1,
              commands_failed: 0,
              lifecycle: [
                { status: 'accepted', at: '2026-02-10T08:00:00Z' },
                { status: 'completed', at: '2026-02-10T08:01:00Z' },
              ],
              result: {
                command_submitted: true,
                command_effect_confirmed: true,
                commands_total: 1,
                commands_effect_confirmed: 1,
                commands_failed: 0,
              },
              timeline: [
                {
                  event_id: 'evt-1',
                  event_type: 'CYCLE_START_INITIATED',
                  at: '2026-02-10T08:00:00Z',
                },
                {
                  event_id: 'evt-2',
                  event_type: 'TANK_LEVEL_CHECKED',
                  reason_code: 'tank_level_checked',
                  at: '2026-02-10T08:00:30Z',
                },
              ],
            },
          },
        })
      }

      return Promise.resolve({
        data: {
          status: 'ok',
          data: [
            {
              task_id: 'st-recent',
              zone_id: 42,
              task_type: 'lighting',
              status: 'running',
              created_at: '2026-02-10T07:59:00Z',
              updated_at: '2026-02-10T08:00:00Z',
              scheduled_for: null,
              correlation_id: null,
              lifecycle: [],
            },
            {
              task_id: 'st-failed',
              zone_id: 42,
              task_type: 'diagnostics',
              status: 'failed',
              updated_at: '2026-02-10T08:00:10Z',
              error_code: 'cycle_start_refill_timeout',
              reason_code: 'cycle_start_refill_timeout',
              lifecycle: [],
            },
            {
              task_id: 'st-done-unconfirmed',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'completed',
              updated_at: '2026-02-10T08:00:20Z',
              action_required: true,
              command_submitted: true,
              command_effect_confirmed: false,
              commands_total: 1,
              commands_effect_confirmed: 0,
              lifecycle: [],
            },
            {
              task_id: 'st-no-commands',
              zone_id: 42,
              task_type: 'diagnostics',
              status: 'completed',
              updated_at: '2026-02-10T08:00:30Z',
              action_required: true,
              commands_total: 0,
              commands_effect_confirmed: 0,
              lifecycle: [],
            },
          ],
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

    const vm = wrapper.vm as any
    expect(vm.telemetryLabel).toBe('24.4°C / 58%')
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

    const vm = wrapper.vm as any
    expect(vm.isSystemTypeLocked).toBe(true)
    expect(wrapper.text()).toContain('Тип системы зафиксирован для активного цикла.')
  })

  it('показывает lifecycle scheduler-task и открывает задачу из списка', async () => {
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

    expect(wrapper.text()).toContain('Scheduler Task Lifecycle')
    expect(wrapper.text()).toContain('st-recent')
    expect(wrapper.text()).toContain('Выполняется')

    const openButton = wrapper.findAll('button').find((btn) => btn.text() === 'Открыть')
    expect(openButton).toBeTruthy()

    await openButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('st-test')
    expect(wrapper.text()).toContain('Решение автоматики')
    expect(wrapper.text()).toContain('Выполнить')
    expect(wrapper.text()).toContain('SLA-контроль')
    expect(wrapper.text()).toContain('SLA выполнен')
    expect(wrapper.text()).toContain('Запуск цикла инициирован')
    expect(wrapper.text()).toContain('Проверка уровня бака выполнена')
    expect(wrapper.text()).toContain('tank_level_checked')
    expect(wrapper.text()).toContain('DONE подтвержден')

    const vm = wrapper.vm as any
    expect(vm.schedulerTaskStatusLabel('expired')).toBe('Просрочена')
    expect(vm.schedulerTaskEventLabel('SCHEDULE_TASK_EXECUTION_STARTED')).toContain('execution started')
    expect(vm.schedulerTaskReasonLabel('task_expired')).toContain('expires_at')
    expect(vm.schedulerTaskErrorLabel('task_due_deadline_exceeded')).toContain('due_at')
    expect(vm.formatDateTime('2026-02-10T08:00:00')).toBe(vm.formatDateTime('2026-02-10T08:00:00Z'))

    const noCommandsMeta = vm.schedulerTaskDoneMeta({
      status: 'completed',
      action_required: true,
      commands_total: 0,
      commands_effect_confirmed: 0,
      result: {},
    })
    expect(noCommandsMeta.label).toContain('Команды не отправлялись')
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

    const editButton = wrapper.findAll('button').find((btn) => btn.text() === 'Редактировать')
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
    })
    await flushPromises()
    expect(vm.climateForm.dayTemp).toBe(30)
  })

  it('санитизирует поврежденный профиль из localStorage', async () => {
    window.localStorage.setItem(
      'zone:42:automation-profile:v2',
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

  it('показывает сообщение при отсутствии timeline event-contract', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/scheduler-tasks/')) {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              task_id: 'st-test',
              zone_id: 42,
              task_type: 'irrigation',
              status: 'completed',
              created_at: '2026-02-10T08:00:00Z',
              updated_at: '2026-02-10T08:01:00Z',
              scheduled_for: '2026-02-10T08:00:00Z',
              due_at: '2026-02-10T08:02:00Z',
              expires_at: '2026-02-10T08:05:00Z',
              correlation_id: null,
              lifecycle: [
                { status: 'accepted', at: '2026-02-10T08:00:00Z' },
                { status: 'completed', at: '2026-02-10T08:01:00Z' },
              ],
              result: {
                command_submitted: true,
                command_effect_confirmed: true,
                commands_total: 1,
                commands_effect_confirmed: 1,
                commands_failed: 0,
              },
            },
          },
        })
      }

      return Promise.resolve({
        data: {
          status: 'ok',
          data: [
            {
              task_id: 'st-recent',
              zone_id: 42,
              task_type: 'lighting',
              status: 'running',
              updated_at: '2026-02-10T08:00:00Z',
              lifecycle: [],
            },
          ],
        },
      })
    })

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 42,
        targets: { ph: { target: 5.8 }, ec: { target: 1.5 } } as any,
      },
    })

    await flushPromises()
    const openButton = wrapper.findAll('button').find((btn) => btn.text() === 'Открыть')
    expect(openButton).toBeTruthy()
    await openButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Timeline событий недоступен')
  })

  it('игнорирует устаревший ответ scheduler-задач после смены зоны', async () => {
    const deferred = <T>() => {
      let resolve!: (value: T) => void
      const promise = new Promise<T>((res) => {
        resolve = res
      })
      return { promise, resolve }
    }

    const zone1Response = deferred<any>()
    const zone2Response = deferred<any>()
    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/api/zones/1/scheduler-tasks')) {
        return zone1Response.promise
      }
      if (url.includes('/api/zones/2/scheduler-tasks')) {
        return zone2Response.promise
      }
      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 1,
        targets: { ph: { target: 5.8 }, ec: { target: 1.5 } } as any,
      },
    })

    await wrapper.setProps({ zoneId: 2 })
    zone2Response.resolve({
      data: {
        status: 'ok',
        data: [
          {
            task_id: 'st-zone-2',
            zone_id: 2,
            task_type: 'irrigation',
            status: 'running',
            updated_at: '2026-02-10T08:01:00Z',
            lifecycle: [],
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('st-zone-2')

    zone1Response.resolve({
      data: {
        status: 'ok',
        data: [
          {
            task_id: 'st-zone-1',
            zone_id: 1,
            task_type: 'irrigation',
            status: 'running',
            updated_at: '2026-02-10T08:00:00Z',
            lifecycle: [],
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('st-zone-2')
    expect(wrapper.text()).not.toContain('st-zone-1')
  })

  it('перезагружает persisted-профиль при смене zoneId', async () => {
    window.localStorage.setItem(
      'zone:1:automation-profile:v2',
      JSON.stringify({
        climate: { dayTemp: 24 },
      })
    )
    window.localStorage.setItem(
      'zone:2:automation-profile:v2',
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
      'zone:2:automation-profile:v2',
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

  it('очищает список scheduler-задач сразу при смене зоны', async () => {
    const deferred = <T>() => {
      let resolve!: (value: T) => void
      const promise = new Promise<T>((res) => {
        resolve = res
      })
      return { promise, resolve }
    }

    const zone1Response = deferred<any>()
    const zone2Response = deferred<any>()
    apiGetMock.mockImplementation((url: string) => {
      if (url.includes('/api/zones/1/scheduler-tasks')) {
        return zone1Response.promise
      }
      if (url.includes('/api/zones/2/scheduler-tasks')) {
        return zone2Response.promise
      }
      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    const wrapper = mount(ZoneAutomationTab, {
      props: {
        zoneId: 1,
        targets: {} as any,
      },
    })

    zone1Response.resolve({
      data: {
        status: 'ok',
        data: [
          {
            task_id: 'st-zone-1',
            zone_id: 1,
            task_type: 'irrigation',
            status: 'running',
            updated_at: '2026-02-10T08:00:00Z',
            lifecycle: [],
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('st-zone-1')

    await wrapper.setProps({ zoneId: 2 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('st-zone-1')

    zone2Response.resolve({
      data: {
        status: 'ok',
        data: [
          {
            task_id: 'st-zone-2',
            zone_id: 2,
            task_type: 'irrigation',
            status: 'running',
            updated_at: '2026-02-10T08:00:30Z',
            lifecycle: [],
          },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('st-zone-2')
  })

  it('фильтрует список scheduler-задач по пресетам и поиску', async () => {
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

    expect(wrapper.text()).toContain('st-recent')
    expect(wrapper.text()).toContain('st-failed')
    expect(wrapper.text()).toContain('st-done-unconfirmed')

    const vm = wrapper.vm as any
    vm.schedulerTaskPreset = 'failed'
    await flushPromises()
    expect(wrapper.text()).toContain('st-failed')
    expect(wrapper.text()).not.toContain('st-recent')

    vm.schedulerTaskPreset = 'done_unconfirmed'
    await flushPromises()
    expect(wrapper.text()).toContain('st-done-unconfirmed')
    expect(wrapper.text()).not.toContain('st-no-commands')

    vm.schedulerTaskSearch = 'st-failed'
    vm.schedulerTaskPreset = 'all'
    await flushPromises()
    expect(wrapper.text()).toContain('st-failed')
    expect(wrapper.text()).not.toContain('st-recent')
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

    const editButton = wrapper.findAll('button').find((btn) => btn.text() === 'Редактировать')
    expect(editButton).toBeUndefined()
  })
})
