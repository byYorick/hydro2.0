import { computed } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ZoneCorrectionCalibrationStack from '../ZoneCorrectionCalibrationStack.vue'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const permission = vi.hoisted(() => ({ edit: true }))
vi.mock('@/composables/useRole', () => ({ useRole: () => ({ canEdit: computed(() => permission.edit) }) }))
const stubs = {
  CorrectionRuntimeReadinessCard: { name: 'Readiness', emits: ['focus-pid-config', 'focus-process-calibration'], template: '<div data-testid="readiness" />' },
  PidConfigForm: { name: 'PidConfigForm', props: ['zoneId', 'disabled', 'phaseTargets'], template: '<div data-testid="pid-editor"><input data-testid="pid-draft" /></div>' },
  PidLogsTable: { template: '<div data-testid="pid-history" />' },
  SensorCalibrationStatus: { template: '<div data-testid="sensors" />' },
  PumpCalibrationsPanel: { template: '<div data-testid="pumps" />' },
  ProcessCalibrationPanel: { template: '<div data-testid="process" />' },
  CorrectionConfigForm: { template: '<div data-testid="limits" />' },
}
function mountStack(showRuntimeReadiness = true) {
  return mount(ZoneCorrectionCalibrationStack, { props: { zoneId: 42, sensorCalibrationSettings: {} as SensorCalibrationSettings, showRuntimeReadiness }, global: { stubs } })
}
describe('AE3 correction workspace', () => {
  beforeEach(() => { permission.edit = true; window.history.replaceState({}, '', '/') })

  it('показывает готовность и загружает редактор только при переходе', async () => {
    const wrapper = mountStack()
    expect(wrapper.find('[data-testid="readiness"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="pid-editor"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === 'PID')!.trigger('click')
    expect(wrapper.find('[data-testid="pid-editor"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="readiness"]').isVisible()).toBe(false)
    expect(wrapper.find('[data-testid="sensors"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('сохраняет черновик открытой формы при переключении разделов коррекции', async () => {
    const wrapper = mountStack()
    const select = (label: string) => wrapper.findAll('button').find(button => button.text() === label)!.trigger('click')
    await select('PID')
    await wrapper.get('[data-testid="pid-draft"]').setValue('0.42')
    await select('Процесс')
    expect(wrapper.get('[data-testid="pid-editor"]').isVisible()).toBe(false)
    await select('PID')
    expect((wrapper.get('[data-testid="pid-draft"]').element as HTMLInputElement).value).toBe('0.42')
    await wrapper.setProps({ zoneId: 43 })
    expect(wrapper.find('[data-testid="pid-editor"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('переходит из проверки готовности к нужной настройке', async () => {
    const wrapper = mountStack()
    wrapper.findComponent({ name: 'Readiness' }).vm.$emit('focus-process-calibration')
    await flushPromises()
    expect(wrapper.find('[data-testid="process"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('открывает канонический PID редактор по прямой ссылке и сохраняет readonly', async () => {
    permission.edit = false
    window.history.replaceState({}, '', '/zones/42?auto=solution#zone-pid-config-panel-shared')
    const wrapper = mountStack()
    await flushPromises()
    expect(wrapper.findComponent({ name: 'PidConfigForm' }).props('disabled')).toBe(true)
    wrapper.unmount()
  })

  it('в мастере без итоговой проверки начинает с датчиков', () => {
    const wrapper = mountStack(false)
    expect(wrapper.find('[data-testid="sensors"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Готовность')
    expect(wrapper.text()).not.toContain('автотюнинг')
    wrapper.unmount()
  })
})
