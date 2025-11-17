import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))
vi.mock('@/Pages/Zones/ZoneCard.vue', () => ({
  default: { name: 'ZoneCard', props: ['zone'], template: '<div class="zone-card">{{ zone.name }}</div>' },
}))

const sampleZones = [
  { id: 1, name: 'Alpha', status: 'RUNNING' },
  { id: 2, name: 'Beta', status: 'PAUSED' },
  { id: 3, name: 'Gamma', status: 'WARNING' },
  { id: 4, name: 'Delta', status: 'RUNNING' },
]

const initFromPropsMock = vi.fn()

vi.mock('@/stores/zones', () => ({
  useZonesStore: () => ({
    items: sampleZones,
    initFromProps: initFromPropsMock,
  }),
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({ props: { zones: sampleZones } }),
}))

import ZonesIndex from '../Index.vue'

describe('Zones/Index.vue', () => {
  beforeEach(() => {
    initFromPropsMock.mockClear()
  })

  it('фильтрует по статусу', async () => {
    const wrapper = mount(ZonesIndex)
    // default: все
    expect(wrapper.findAll('.zone-card').length).toBe(4)
    // set status = RUNNING
    const select = wrapper.find('select')
    await select.setValue('RUNNING')
    const names = wrapper.findAll('.zone-card').map((w) => w.text())
    expect(names).toEqual(['Alpha', 'Delta'])
  })

  it('фильтрует по строке поиска', async () => {
    const wrapper = mount(ZonesIndex)
    const input = wrapper.find('input')
    await input.setValue('ga')
    const names = wrapper.findAll('.zone-card').map((w) => w.text())
    expect(names).toEqual(['Gamma'])
  })

  it('показывает пустое состояние при отсутствии результатов', async () => {
    const wrapper = mount(ZonesIndex)
    await wrapper.find('input').setValue('no-match-here')
    expect(wrapper.text()).toContain('Нет зон по текущим фильтрам')
  })
})


