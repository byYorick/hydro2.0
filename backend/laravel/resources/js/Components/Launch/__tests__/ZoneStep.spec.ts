import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({
  api: {
    greenhouses: {
      list: vi.fn(),
    },
    zones: {
      list: vi.fn(),
      create: vi.fn(),
    },
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

vi.mock('@inertiajs/vue3', () => ({
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import { api } from '@/services/api'
import {
  _resetLaunchPreferencesForTests,
} from '@/composables/useLaunchPreferences'
import ZoneStep from '../ZoneStep.vue'

describe('ZoneStep', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
    vi.mocked(api.greenhouses.list).mockResolvedValue([
      { id: 1, uid: 'gh-01', name: 'Berry', type: 'Плёночная' },
      { id: 2, uid: 'gh-02', name: 'Leafy', type: 'Стеклянная' },
    ] as any)
    vi.mocked(api.zones.list).mockResolvedValue([
      { id: 10, name: 'Zone A', greenhouse_id: 1, status: 'RUNNING' },
      { id: 11, name: 'Zone B', greenhouse_id: 1, status: 'DRAFT' },
      { id: 20, name: 'Zone C', greenhouse_id: 2, status: 'IDLE' },
    ] as any)
  })

  it('renders Теплица card and CTA to /greenhouses', async () => {
    const w = mount(ZoneStep, { props: { modelValue: null } })
    await flushPromises()
    expect(w.text()).toContain('Теплица')
    expect(w.text()).toContain('Нужна новая теплица?')
    const ghLink = w.find('a[href="/greenhouses"]')
    expect(ghLink.exists()).toBe(true)
  })

  it('hides Зона card until greenhouse is selected', async () => {
    // 2 greenhouses → no auto-select
    const w = mount(ZoneStep, { props: { modelValue: null } })
    await flushPromises()
    expect(w.text()).not.toContain('Zone A')
    // выбираем теплицу → зона появляется
    await w.find('select').setValue('1')
    await flushPromises()
    expect(w.text()).toContain('Zone A')
  })

  it('auto-selects greenhouse when only one is available', async () => {
    vi.mocked(api.greenhouses.list).mockResolvedValue([
      { id: 7, uid: 'gh-only', name: 'Solo', type: 'NFT' },
    ] as any)
    vi.mocked(api.zones.list).mockResolvedValue([
      { id: 70, name: 'Zone X', greenhouse_id: 7, status: 'RUNNING' },
    ] as any)

    const w = mount(ZoneStep, { props: { modelValue: null } })
    await flushPromises()
    expect(w.text()).toContain('Solo')
    expect(w.text()).toContain('Zone X')
  })

  it('emits update:modelValue when zone is picked from list', async () => {
    const w = mount(ZoneStep, { props: { modelValue: null } })
    await flushPromises()
    // greenhouse 1 must be selected manually (2 available, no auto-select)
    const select = w.find('select')
    await select.setValue('1')
    await flushPromises()

    const buttons = w.findAll('button').filter((b) => b.text().includes('Zone A'))
    expect(buttons.length).toBeGreaterThan(0)
    await buttons[0].trigger('click')

    expect(w.emitted('update:modelValue')).toBeTruthy()
    expect(w.emitted('update:modelValue')![0]).toEqual([10])
  })

  it('auto-selects greenhouse from initial zone modelValue', async () => {
    const w = mount(ZoneStep, { props: { modelValue: 20 } })
    await flushPromises()
    expect(w.text()).toContain('Leafy')
    expect(w.text()).toContain('Zone C')
  })
})
