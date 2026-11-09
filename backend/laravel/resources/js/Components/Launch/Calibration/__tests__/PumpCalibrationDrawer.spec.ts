import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PumpCalibrationDrawer from '../PumpCalibrationDrawer.vue'
import type { Device } from '@/types'
import type { PumpCalibration } from '@/types/PidConfig'

function makePump(overrides: Partial<PumpCalibration>): PumpCalibration {
  return {
    node_channel_id: 0,
    role: 'pump_a',
    component: 'NPK',
    channel_label: 'node · pump_a',
    node_uid: 'node-1',
    channel: 'pump_a',
    ml_per_sec: null,
    k_ms_per_ml_l: null,
    source: null,
    valid_from: null,
    is_active: true,
    ...overrides,
  }
}

describe('PumpCalibrationDrawer', () => {
  it('не перезаписывает initialComponent при пустом initialNodeChannelId', () => {
    const devices: Device[] = [
      {
        id: 1,
        uid: 'node-1',
        type: 'ph',
        status: 'online',
        channels: [
          { id: 101, channel: 'pump_a', type: 'ACTUATOR', metric: null, unit: null },
          { id: 202, channel: 'pump_acid', type: 'ACTUATOR', metric: null, unit: null },
        ],
      },
    ]

    const pumps: PumpCalibration[] = [
      makePump({ role: 'pump_a', node_channel_id: 101, channel: 'pump_a', component: 'NPK' }),
      makePump({ role: 'pump_acid', node_channel_id: 202, channel: 'pump_acid', component: 'pH Down' }),
    ]

    const w = mount(PumpCalibrationDrawer, {
      props: {
        show: true,
        zoneId: 7,
        devices,
        pumps,
        initialComponent: 'ph_down',
        initialNodeChannelId: null,
      },
      global: {
        stubs: {
          teleport: true,
          transition: false,
        },
      },
    })

    expect(w.text()).toContain('pH Down')
    expect(w.text()).toContain('node-1 · pump_acid')
    expect(w.text()).toContain('ch202')
    expect(w.text()).not.toContain('ch101')
  })
})

function mountFlow() {
  return mount(PumpCalibrationDrawer, {
    props: { show: true, zoneId: 7, devices: [{ id: 1, uid: 'node-1', type: 'ph', status: 'online', channels: [{ id: 202, channel: 'pump_acid', type: 'ACTUATOR', metric: null, unit: null }] }], pumps: [], initialComponent: 'ph_down', initialNodeChannelId: 202 },
    global: { stubs: { teleport: true, transition: false } },
  })
}
function button(wrapper: ReturnType<typeof mountFlow>, label: string) {
  return wrapper.findAll('button').find(item => item.text() === label)!
}

it('сохраняет внешний замер только после проверки и явного выбора ручного режима', async () => {
  const wrapper = mountFlow()
  await button(wrapper, 'Использовать внешний замер без запуска').trigger('click')
  expect(wrapper.emitted('start')).toBeUndefined()
  await wrapper.findAll('input[type="number"]')[0].setValue('40')
  expect(button(wrapper, 'Проверить результат').attributes('disabled')).toBeDefined()
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await button(wrapper, 'Проверить результат').trigger('click')
  expect(wrapper.text()).toContain('2.000')
  await button(wrapper, 'Назад').trigger('click')
  expect((wrapper.findAll('input[type="number"]')[0].element as HTMLInputElement).value).toBe('40')
  await button(wrapper, 'Проверить результат').trigger('click')
  await button(wrapper, 'К сохранению').trigger('click')
  await button(wrapper, 'Сохранить результат').trigger('click')
  expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ component: 'ph_down', node_channel_id: 202, duration_sec: 20, actual_ml: 40, skip_run: true, manual_override: true })
  expect(wrapper.text()).not.toContain('Сохранение подтверждено сервером')
  await wrapper.setProps({ saveSuccessSeq: 1 })
  expect(wrapper.text()).toContain('Сохранение подтверждено сервером')
  await button(wrapper, 'Закрыть').trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
  wrapper.unmount()
})

it('не теряет введённый объём при попытке закрыть окно', async () => {
  const wrapper = mountFlow()
  await button(wrapper, 'Использовать внешний замер без запуска').trigger('click')
  await wrapper.findAll('input[type="number"]')[0].setValue('40')
  await wrapper.get('button[aria-label="Закрыть окно"]').trigger('click')
  expect(wrapper.emitted('close')).toBeUndefined()
  expect(wrapper.text()).toContain('Закрыть без сохранения')
  await button(wrapper, 'Продолжить работу').trigger('click')
  expect((wrapper.findAll('input[type="number"]')[0].element as HTMLInputElement).value).toBe('40')
  await wrapper.get('button[aria-label="Закрыть окно"]').trigger('click')
  await button(wrapper, 'Закрыть без сохранения').trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
  wrapper.unmount()
})

it('передаёт подтверждённый токен запуска и не подменяет его ручным переопределением', async () => {
  const wrapper = mountFlow()
  await button(wrapper, 'Запустить замер').trigger('click')
  expect(wrapper.emitted('start')?.[0]?.[0]).toEqual({ component: 'ph_down', node_channel_id: 202, duration_sec: 20 })
  await wrapper.setProps({ runSuccessSeq: 1, lastRunToken: 'run-token' })
  await wrapper.findAll('input[type="number"]')[0].setValue('35')
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await button(wrapper, 'Проверить результат').trigger('click')
  await button(wrapper, 'К сохранению').trigger('click')
  await button(wrapper, 'Сохранить результат').trigger('click')
  const payload = wrapper.emitted('save')?.[0]?.[0]
  expect(payload).toMatchObject({ run_token: 'run-token', actual_ml: 35, skip_run: true })
  expect(payload).not.toHaveProperty('manual_override')
  await wrapper.get('button[aria-label="Закрыть окно"]').trigger('click')
  expect(wrapper.emitted('close')).toBeUndefined()
  wrapper.unmount()
})
