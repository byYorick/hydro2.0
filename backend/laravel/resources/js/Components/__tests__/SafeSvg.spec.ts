import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SafeSvg from '../SafeSvg.vue'

describe('SafeSvg', () => {
  it('рисует path без v-html и отбрасывает посторонние теги', () => {
    const wrapper = mount(SafeSvg, {
      props: {
        markup: '<path d="M1 1h2"/><script>alert(1)</script>',
      },
    })

    expect(wrapper.find('path').attributes('d')).toBe('M1 1h2')
    expect(wrapper.html()).not.toContain('script')
    expect(wrapper.html()).not.toContain('alert')
  })

  it('снимает внешний svg и оставляет фигуры', () => {
    const wrapper = mount(SafeSvg, {
      props: {
        markup: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/></svg>',
      },
    })

    expect(wrapper.find('circle').attributes('r')).toBe('4')
    expect(wrapper.findAll('svg')).toHaveLength(1)
  })
})
