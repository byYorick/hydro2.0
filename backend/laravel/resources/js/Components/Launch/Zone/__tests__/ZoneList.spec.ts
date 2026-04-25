import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ZoneList from '../ZoneList.vue'
import type { ZoneListItem } from '../ZoneList.vue'

const zones: ZoneListItem[] = [
  { id: 1, name: 'Zone A', status: 'RUNNING', description: 'tomato' },
  { id: 2, name: 'Zone B', status: 'DRAFT' },
  { id: 3, name: 'Zone C', status: null },
]

describe('ZoneList', () => {
  it('renders all zones with names and descriptions', () => {
    const w = mount(ZoneList, { props: { zones } })
    expect(w.text()).toContain('Zone A')
    expect(w.text()).toContain('tomato')
    expect(w.text()).toContain('Zone B')
    expect(w.text()).toContain('Zone C')
  })

  it('emits pick(id) when row is clicked', async () => {
    const w = mount(ZoneList, { props: { zones } })
    const rows = w.findAll('button')
    await rows[1].trigger('click')
    expect(w.emitted('pick')).toBeTruthy()
    expect(w.emitted('pick')![0]).toEqual([2])
  })

  it('marks active row with aria-current', () => {
    const w = mount(ZoneList, { props: { zones, activeId: 2 } })
    const rows = w.findAll('button')
    expect(rows[0].attributes('aria-current')).toBeUndefined()
    expect(rows[1].attributes('aria-current')).toBe('true')
  })

  it('renders empty placeholder when zones=[]', () => {
    const w = mount(ZoneList, { props: { zones: [] } })
    expect(w.text()).toContain('нет зон')
  })

  it('maps RUNNING → активна (growth tone)', () => {
    const w = mount(ZoneList, { props: { zones: [zones[0]] } })
    expect(w.text()).toContain('активна')
  })

  it('maps DRAFT → черновик (warn tone)', () => {
    const w = mount(ZoneList, { props: { zones: [zones[1]] } })
    expect(w.text()).toContain('черновик')
  })
})
