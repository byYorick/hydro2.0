import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationRuntimeMetrics from '../AutomationRuntimeMetrics.vue'
const props = { automationState: null, cleanTankLevel: null, nutrientTankLevel: 0, bufferTankLevel: 0, isPumpInActive: false, isCirculationActive: false, isPhCorrectionActive: false, isEcCorrectionActive: false, isIrrigationActive: false }
describe('runtime measurement evidence', () => {
  it('shows unknown levels separately from zero and retains an empty buffer reading', () => {
    const wrapper = mount(AutomationRuntimeMetrics, { props })
    expect(wrapper.text()).toContain('Нет данных')
    expect(wrapper.text()).toContain('Буфер')
    expect(wrapper.findAll('dd').map(x => x.text())).toEqual(['Нет данных', '0%', '0%', '—', '—'])
  })
  it('labels a discrete upper sensor as a threshold rather than an exact percentage', () => {
    const wrapper = mount(AutomationRuntimeMetrics, { props: { ...props, automationState: { irr_node_state: { clean_level_max: true } } as any, cleanTankLevel: 100 } })
    expect(wrapper.text()).toContain('Достигнута верхняя отметка')
    expect(wrapper.text()).not.toContain('100%')
  })
})
