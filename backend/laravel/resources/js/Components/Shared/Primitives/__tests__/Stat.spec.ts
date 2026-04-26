import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Stat from '../Stat.vue'

describe('Stat', () => {
  it('renders label and value', () => {
    const w = mount(Stat, { props: { label: 'pH target', value: '5.8' } })
    expect(w.text()).toContain('pH target')
    expect(w.text()).toContain('5.8')
  })

  it('applies brand tone class', () => {
    const w = mount(Stat, {
      props: { label: 'X', value: '1', tone: 'brand' },
    })
    expect(w.html()).toContain('text-brand-ink')
  })

  it('applies font-mono when mono prop is true', () => {
    const w = mount(Stat, {
      props: { label: 'X', value: '42', mono: true },
    })
    expect(w.html()).toContain('font-mono')
  })
})
