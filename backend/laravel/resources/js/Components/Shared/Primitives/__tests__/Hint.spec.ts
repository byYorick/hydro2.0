import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Hint from '../Hint.vue'

describe('Hint', () => {
  it('renders slot content when show is undefined (default visible)', () => {
    const w = mount(Hint, { slots: { default: 'инфо' } })
    expect(w.text()).toContain('инфо')
  })

  it('renders when show=true', () => {
    const w = mount(Hint, { props: { show: true }, slots: { default: 'on' } })
    expect(w.text()).toContain('on')
  })

  it('hides when show=false', () => {
    const w = mount(Hint, { props: { show: false }, slots: { default: 'hidden' } })
    expect(w.text()).toBe('')
    expect(w.html()).toBe('<!--v-if-->')
  })
})
