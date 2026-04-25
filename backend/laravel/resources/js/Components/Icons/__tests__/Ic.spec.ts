import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Ic from '../Ic.vue'

describe('Ic', () => {
  it('renders SVG with default 14px size', () => {
    const w = mount(Ic, { props: { name: 'check' } })
    const svg = w.find('svg')
    expect(svg.attributes('width')).toBe('14')
    expect(svg.attributes('height')).toBe('14')
  })

  it('respects size token sm/lg/xl', () => {
    const w1 = mount(Ic, { props: { name: 'check', size: 'sm' } })
    expect(w1.find('svg').attributes('width')).toBe('12')

    const w2 = mount(Ic, { props: { name: 'play', size: 'lg' } })
    expect(w2.find('svg').attributes('width')).toBe('16')

    const w3 = mount(Ic, { props: { name: 'play', size: 'xl' } })
    expect(w3.find('svg').attributes('width')).toBe('20')
  })

  it('respects numeric size', () => {
    const w = mount(Ic, { props: { name: 'check', size: 24 } })
    expect(w.find('svg').attributes('width')).toBe('24')
  })

  it('uses fill=none + stroke=currentColor for stroked icons', () => {
    const w = mount(Ic, { props: { name: 'beaker' } })
    const svg = w.find('svg')
    expect(svg.attributes('fill')).toBe('none')
    expect(svg.attributes('stroke')).toBe('currentColor')
  })

  it('uses fill=currentColor for play/dot (filled icons)', () => {
    const w = mount(Ic, { props: { name: 'dot' } })
    expect(w.find('svg').attributes('fill')).toBe('currentColor')
  })

  it('inlines path body', () => {
    const w = mount(Ic, { props: { name: 'check' } })
    expect(w.html()).toContain('d="M3 8.5l3 3 7-7"')
  })

  it('all 21 icon names are renderable without errors', () => {
    const names = [
      'check', 'x', 'plus', 'chev', 'chevDown',
      'info', 'warn', 'play', 'drop', 'leaf',
      'chip', 'gh', 'grid', 'beaker', 'wave',
      'zap', 'dot', 'edit', 'reload', 'lock', 'bookmark',
    ] as const
    for (const name of names) {
      const w = mount(Ic, { props: { name } })
      expect(w.find('svg').exists()).toBe(true)
    }
  })
})
