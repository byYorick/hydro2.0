import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CockpitLayout from '../CockpitLayout.vue'

describe('CockpitLayout.vue', () => {
  it('рендерит три колонки через именованные слоты', () => {
    const wrapper = mount(CockpitLayout, {
      slots: {
        left: '<div data-testid="slot-left">LEFT</div>',
        center: '<div data-testid="slot-center">CENTER</div>',
        right: '<div data-testid="slot-right">RIGHT</div>',
      },
    })

    expect(wrapper.find('[data-testid="scheduler-cockpit-layout"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="slot-left"]').text()).toBe('LEFT')
    expect(wrapper.get('[data-testid="slot-center"]').text()).toBe('CENTER')
    expect(wrapper.get('[data-testid="slot-right"]').text()).toBe('RIGHT')
  })
})
