import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PidChart from '../PidChart.vue'

describe('PidChart', () => {
  it('renders SVG with target/dead/close/far values', () => {
    const w = mount(PidChart, {
      props: { target: 5.8, dead: 0.05, close: 0.3, far: 1.0 },
    })
    expect(w.find('svg').exists()).toBe(true)
    const html = w.html()
    expect(html).toContain('target 5.8')
    expect(html).toContain('−1')
    expect(html).toContain('+1')
  })

  it('uses custom axisLabel', () => {
    const w = mount(PidChart, {
      props: { target: 1.6, dead: 0.1, close: 0.5, far: 1.5, axisLabel: 'EC' },
    })
    expect(w.text()).toContain('EC')
  })

  it('renders 3 zone-rectangles + target line', () => {
    const w = mount(PidChart, {
      props: { target: 5.8, dead: 0.05, close: 0.3, far: 1.0 },
    })
    expect(w.findAll('rect')).toHaveLength(3)
    expect(w.findAll('line')).toHaveLength(1)
  })

  it('handles far=0 gracefully (no division by zero)', () => {
    const w = mount(PidChart, {
      props: { target: 5.8, dead: 0, close: 0, far: 0 },
    })
    expect(w.find('svg').exists()).toBe(true)
  })
})
