import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Chip from '../Chip.vue'

describe('Chip', () => {
  it('renders default slot', () => {
    const w = mount(Chip, { slots: { default: 'online' } })
    expect(w.text()).toBe('online')
  })

  it('applies tone classes for growth', () => {
    const w = mount(Chip, { props: { tone: 'growth' }, slots: { default: 'ok' } })
    expect(w.classes()).toContain('bg-growth-soft')
    expect(w.classes()).toContain('text-growth')
  })

  it('falls back to neutral when tone omitted', () => {
    const w = mount(Chip, { slots: { default: 'idle' } })
    expect(w.classes().some((c) => c.includes('bg-[var(--bg-elevated)]'))).toBe(true)
  })

  it('принимает общий тон offline, не ломая growth', () => {
    const offline = mount(Chip, { props: { tone: 'offline' }, slots: { default: 'нет связи' } })
    const growth = mount(Chip, { props: { tone: 'growth' }, slots: { default: 'ok' } })
    expect(offline.classes()).toContain('tone-offline')
    expect(growth.classes()).toContain('bg-growth-soft')
    expect(offline.classes()).not.toContain('bg-growth-soft')
  })

  it('renders icon slot', () => {
    const w = mount(Chip, {
      props: { tone: 'brand' },
      slots: { icon: '<svg data-test="ic"></svg>', default: 'AE3' },
    })
    expect(w.find('[data-test="ic"]').exists()).toBe(true)
    expect(w.text()).toContain('AE3')
  })
})
