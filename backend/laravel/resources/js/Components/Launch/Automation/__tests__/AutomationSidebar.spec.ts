import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationSidebar from '../AutomationSidebar.vue'
import type { AutomationNavMap } from '../AutomationSidebar.vue'

const baseNav: AutomationNavMap = {
  bindings: { state: 'blocker', count: '1/3' },
  contour: { state: 'active', count: '0/2' },
  irrigation: { state: 'passed', count: '2/2' },
  correction: { state: 'active', count: '1/2' },
  lighting: { state: 'optional', count: 'опц.' },
  climate: { state: 'optional', count: 'опц.' },
}

describe('AutomationSidebar', () => {
  it('renders 6 nav items in 3 groups with titles', () => {
    const w = mount(AutomationSidebar, {
      props: { current: 'bindings', nav: baseNav },
    })
    expect(w.text()).toContain('Инфраструктура')
    expect(w.text()).toContain('Подсистемы')
    expect(w.text()).toContain('Опциональные')
    expect(w.text()).toContain('Привязки узлов')
    expect(w.text()).toContain('Водный контур')
    expect(w.text()).toContain('Полив')
    expect(w.text()).toContain('Коррекция pH/EC')
    expect(w.text()).toContain('Свет')
    expect(w.text()).toContain('Климат зоны')
  })

  it('shows ! bullet for blockers, ✓ for passed, idx for active/optional', () => {
    const w = mount(AutomationSidebar, {
      props: { current: 'bindings', nav: baseNav },
    })
    const html = w.html()
    expect(html).toContain('!')
    expect(html).toContain('✓')
  })

  it('emits select(id) on item click', async () => {
    const w = mount(AutomationSidebar, {
      props: { current: 'bindings', nav: baseNav },
    })
    const buttons = w.findAll('button').filter((b) => b.text().includes('Полив'))
    await buttons[0].trigger('click')
    expect(w.emitted('select')).toBeTruthy()
    expect(w.emitted('select')![0]).toEqual(['irrigation'])
  })

  it('marks current with aria-current="page"', () => {
    const w = mount(AutomationSidebar, {
      props: { current: 'irrigation', nav: baseNav },
    })
    const buttons = w.findAll('button')
    const irr = buttons.find((b) => b.text().includes('Полив'))!
    expect(irr.attributes('aria-current')).toBe('page')
  })

  it('renders subtitle from nav.subtitle when provided', () => {
    const navWithSub: AutomationNavMap = {
      ...baseNav,
      contour: { state: 'active', count: '0/2', subtitle: 'NFT · 2 бак(а)' },
    }
    const w = mount(AutomationSidebar, {
      props: { current: 'contour', nav: navWithSub },
    })
    expect(w.text()).toContain('NFT · 2 бак(а)')
  })
})
