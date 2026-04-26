import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ShellCard from '../ShellCard.vue'

describe('ShellCard', () => {
  it('renders title prop', () => {
    const w = mount(ShellCard, { props: { title: 'Теплица' } })
    expect(w.text()).toContain('Теплица')
    expect(w.find('header').exists()).toBe(true)
  })

  it('omits header when no title and no slots', () => {
    const w = mount(ShellCard)
    expect(w.find('header').exists()).toBe(false)
  })

  it('renders title slot taking precedence', () => {
    const w = mount(ShellCard, {
      props: { title: 'fallback' },
      slots: { title: '<span data-test="custom">CUSTOM</span>' },
    })
    expect(w.find('[data-test="custom"]').exists()).toBe(true)
  })

  it('renders actions slot in header', () => {
    const w = mount(ShellCard, {
      props: { title: 'X' },
      slots: { actions: '<button data-test="act">act</button>' },
    })
    expect(w.find('[data-test="act"]').exists()).toBe(true)
  })

  it('drops body padding when pad=false', () => {
    const w = mount(ShellCard, {
      props: { pad: false },
      slots: { default: '<div data-test="body" />' },
    })
    const body = w.find('[data-test="body"]').element.parentElement!
    expect(body.className).not.toContain('p-3.5')
  })
})
