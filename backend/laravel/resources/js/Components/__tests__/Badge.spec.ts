import { mount } from '@vue/test-utils'
import Badge from '../Badge.vue'

describe('Badge', () => {
  it('renders slot content', () => {
    const w = mount(Badge, { slots: { default: 'OK' } })
    expect(w.text()).toContain('OK')
  })
  it('applies variant classes', () => {
    const w = mount(Badge, { props: { variant: 'success' }, slots: { default: 'OK' } })
    expect(w.classes()).toContain('badge--success')
  })

  it('отличает критический и offline бейджи', () => {
    const critical = mount(Badge, { props: { variant: 'critical' }, slots: { default: 'Критично' } })
    const offline = mount(Badge, { props: { variant: 'offline' }, slots: { default: 'Нет связи' } })
    expect(critical.classes()).toContain('badge--critical')
    expect(offline.classes()).toContain('badge--offline')
  })
})
