import { mount } from '@vue/test-utils'
import Badge from '../Badge.vue'

describe('Badge', () => {
  it('renders slot content', () => {
    const w = mount(Badge, { slots: { default: 'OK' } })
    expect(w.text()).toContain('OK')
  })
  it('applies variant classes', () => {
    const w = mount(Badge, { props: { variant: 'success' }, slots: { default: 'OK' } })
    expect(w.classes().join(' ')).toContain('bg-emerald')
  })
})

