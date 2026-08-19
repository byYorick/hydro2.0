import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const pageState = vi.hoisted(() => ({
  url: '/zones/83?tab=cycle',
  props: {
    auth: { user: { role: 'admin' } },
    zone: { name: 'E2E Automation Zone' },
  } as Record<string, unknown>,
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => pageState,
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import Breadcrumbs from '../Breadcrumbs.vue'

describe('Breadcrumbs.vue', () => {
  it('не включает query string в метку числового ID', () => {
    const wrapper = mount(Breadcrumbs)

    expect(wrapper.text()).toContain('E2E Automation Zone')
    expect(wrapper.text()).not.toContain('tab=cycle')
    expect(wrapper.text()).not.toContain('83?')
  })

  it('пропускает сегмент login в крошках', () => {
    pageState.url = '/login'
    pageState.props = { auth: { user: { role: 'admin' } } }

    const wrapper = mount(Breadcrumbs)

    expect(wrapper.text()).toBe('Система')
    expect(wrapper.text()).not.toContain('Login')
  })
})
