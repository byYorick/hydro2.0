import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ConfigOnlyFooter from '../ConfigOnlyFooter.vue'

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span class="stub-badge"><slot /></span>',
  },
}))

describe('ConfigOnlyFooter.vue', () => {
  it('не рендерится, если нет lanes', () => {
    const wrapper = mount(ConfigOnlyFooter, { props: { lanes: [] } })
    expect(wrapper.find('[data-testid="scheduler-config-only"]').exists()).toBe(false)
  })

  it('рендерит бейджи для переданных lanes (строки и объекты)', () => {
    const wrapper = mount(ConfigOnlyFooter, {
      props: {
        lanes: ['ec_correction', { task_type: 'climate', label: 'Климат' }],
      },
    })
    expect(wrapper.find('[data-testid="scheduler-config-only"]').exists()).toBe(true)
    const badges = wrapper.findAll('.stub-badge')
    expect(badges).toHaveLength(2)
    expect(badges[0].text()).toBe('ec_correction')
    expect(badges[1].text()).toBe('Климат')
  })
})
