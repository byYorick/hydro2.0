import { defineComponent, ref } from 'vue'
import { mount, DOMWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import SensorCalibrationDrawer from '../SensorCalibrationDrawer.vue'
import type { SensorCalibrationOverview } from '@/types/SensorCalibration'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const Core = defineComponent({
  name: 'SensorCalibrationWizardCore',
  setup() { return { reference: ref('4.01') } },
  template: '<div><input v-model="reference" aria-label="Эталон" /></div>',
})
function mountDrawer() {
  const items = [11, 12].map(id => ({ node_channel_id: id, node_uid: 'node-1', channel_uid: `ph_${id}`, sensor_type: 'ph', calibration_status: 'never', active_calibration_id: null })) as SensorCalibrationOverview[]
  return mount(SensorCalibrationDrawer, {
    props: { show: true, zoneId: 1, items, settings: {} as SensorCalibrationSettings },
    attachTo: document.body,
    global: { stubs: { SensorCalibrationWizardCore: Core } },
  })
}

afterEach(() => { document.body.innerHTML = '' })

describe('SensorCalibrationDrawer', () => {
  it('сохраняет форму при отказе от закрытия и не отменяет активную сессию', async () => {
    const wrapper = mountDrawer()
    const dom = new DOMWrapper(document.body)
    const core = wrapper.findComponent(Core)
    await core.get('input').setValue('4.10')
    core.vm.$emit('state-change', { hasUnsavedInput: true, activeSession: true, busy: false })
    await dom.get('button[aria-label="Закрыть окно"]').trigger('click')
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(wrapper.findComponent(Core).element).toBe(core.element)
    await dom.findAll('button').find(button => button.text() === 'Продолжить работу')!.trigger('click')
    expect((dom.get('input').element as HTMLInputElement).value).toBe('4.10')
    await dom.get('button[aria-label="Закрыть окно"]').trigger('click')
    await dom.findAll('button').find(button => button.text() === 'Закрыть без сохранения')!.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
  it('меняет канал с несохранёнными данными только после явного выбора', async () => {
    const wrapper = mountDrawer()
    const dom = new DOMWrapper(document.body)
    const core = wrapper.findComponent(Core)
    core.vm.$emit('state-change', { hasUnsavedInput: true, activeSession: false, busy: false })
    await dom.get('select').setValue('12')
    expect(wrapper.findComponent(Core).element).toBe(core.element)
    expect((dom.get('select').element as HTMLSelectElement).value).toBe('11')
    await dom.findAll('button').find(button => button.text() === 'Перейти без сохранения')!.trigger('click')
    expect((dom.get('select').element as HTMLSelectElement).value).toBe('12')
    expect(wrapper.findComponent(Core).element).not.toBe(core.element)
    wrapper.unmount()
  })
})
