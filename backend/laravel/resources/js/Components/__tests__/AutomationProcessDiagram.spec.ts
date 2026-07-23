import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AutomationProcessDiagram from '@/Components/AutomationProcessDiagram.vue'

const baseProps = {
  flowOffset: 0.5,
  cleanTankLevel: 40,
  nutrientTankLevel: 60,
  bufferTankLevel: 0,
  isPumpInActive: false,
  isCirculationActive: true,
  isPhCorrectionActive: false,
  isEcCorrectionActive: false,
  activeDoseChannels: [] as string[],
  isWaterInletActive: false,
  isCleanSupplyActive: false,
  isSolutionSupplyActive: true,
  isTankRefillActive: true,
  isIrrigationActive: false,
  isProcessActive: true,
  automationState: null,
  irrNodeState: null,
}

describe('AutomationProcessDiagram correction pumps', () => {
  it('подсвечивает блок pH без pulse насосов на wait-step', () => {
    const wrapper = mount(AutomationProcessDiagram, {
      props: {
        ...baseProps,
        isPhCorrectionActive: true,
        activeDoseChannels: [],
      },
    })

    const blocks = wrapper.findAll('.correction-block')
    expect(blocks).toHaveLength(2)
    expect(blocks[0].classes()).toContain('correction-block--active')
    expect(blocks[1].classes()).not.toContain('correction-block--active')
    expect(wrapper.findAll('.dose-pump--running')).toHaveLength(0)
    expect(wrapper.text()).toContain('acid')
    expect(wrapper.text()).toContain('base')
  })

  it('пульсирует только активные EC-насосы при corr_dose', () => {
    const wrapper = mount(AutomationProcessDiagram, {
      props: {
        ...baseProps,
        isEcCorrectionActive: true,
        activeDoseChannels: ['pump_b', 'pump_d'],
      },
    })

    const blocks = wrapper.findAll('.correction-block')
    expect(blocks[1].classes()).toContain('correction-block--active')
    expect(wrapper.findAll('.dose-pump--running')).toHaveLength(2)
    expect(wrapper.text()).toContain('A')
    expect(wrapper.text()).toContain('B')
    expect(wrapper.text()).toContain('C')
    expect(wrapper.text()).toContain('D')
  })

  it('показывает PID и калибровку в tooltip при hover на насос', async () => {
    const wrapper = mount(AutomationProcessDiagram, {
      props: {
        ...baseProps,
        pumpHoverByChannel: {
          pump_acid: {
            channel: 'pump_acid',
            controller: 'ph',
            component: 'ph_down',
            node_uid: 'nd-ph',
            ml_per_sec: 0.9,
            k_ms_per_ml_l: null,
            kp: 1.1,
            ki: 0.2,
            kd: 0.05,
            dead_zone: 0.1,
            max_dose_ml: 5,
            min_interval_sec: 90,
          },
        },
      },
      attachTo: document.body,
    })

    const pumpHit = wrapper.findAll('.dose-pump-hit')[0]
    await pumpHit.trigger('mouseenter', { clientX: 10, clientY: 20 })
    await wrapper.vm.$nextTick()

    const tooltip = document.body.querySelector('.details-tooltip')
    expect(tooltip).not.toBeNull()
    expect(tooltip?.textContent).toContain('pump_acid')
    expect(tooltip?.textContent).toContain('мл/с')
    expect(tooltip?.textContent).toContain('0.9')
    expect(tooltip?.textContent).toContain('Kp=1.1')

    wrapper.unmount()
  })
})
