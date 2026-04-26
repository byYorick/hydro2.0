import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StepHeader from '../StepHeader.vue'

describe('StepHeader', () => {
  it('renders step label and sub', () => {
    const w = mount(StepHeader, {
      props: {
        step: { id: 'zone', label: 'Зона', sub: 'теплица + зона' },
        index: 0,
        total: 5,
      },
    })
    expect(w.text()).toContain('Зона')
    expect(w.text()).toContain('теплица + зона')
    expect(w.text()).toContain('1/5')
  })

  it('renders right slot when provided', () => {
    const w = mount(StepHeader, {
      props: {
        step: { id: 'zone', label: 'Зона', sub: 's' },
        index: 0,
        total: 5,
      },
      slots: { right: '<span data-test="right">RIGHT</span>' },
    })
    expect(w.find('[data-test="right"]').exists()).toBe(true)
  })
})
