import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import AppLayout from '../AppLayout.vue'

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    url: '/dashboard',
    props: { auth: { user: { id: 1, name: 'Test' } } },
  }),
  Link: { name: 'Link', template: '<a><slot /></a>' },
}))

vi.mock('@/composables/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: vi.fn(),
}))

vi.mock('@/Components/CommandPalette.vue', () => ({
  default: { name: 'CommandPalette', template: '<div />' },
}))
vi.mock('@/Components/RoleBasedNavigation.vue', () => ({
  default: { name: 'RoleBasedNavigation', template: '<nav />' },
}))
vi.mock('@/Components/Breadcrumbs.vue', () => ({
  default: { name: 'Breadcrumbs', template: '<div />' },
}))
vi.mock('@/Components/HeaderStatusBar.vue', () => ({
  default: { name: 'HeaderStatusBar', template: '<div />' },
}))
vi.mock('@/Components/ErrorBoundary.vue', () => ({
  default: { name: 'ErrorBoundary', template: '<div><slot /></div>' },
}))
vi.mock('@/Components/ToastContainer.vue', () => ({
  default: { name: 'ToastContainer', template: '<div />' },
}))
vi.mock('@/Components/MobileNavigation.vue', () => ({
  default: { name: 'MobileNavigation', template: '<div />' },
}))
vi.mock('@/Components/FavoritesWidget.vue', () => ({
  default: { name: 'FavoritesWidget', template: '<div data-testid="favorites" />' },
}))
vi.mock('@/Components/HistoryWidget.vue', () => ({
  default: { name: 'HistoryWidget', template: '<div data-testid="history" />' },
}))
vi.mock('@/Components/UserMenu.vue', () => ({
  default: { name: 'UserMenu', template: '<div />' },
}))

describe('AppLayout.vue — events rail', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('сворачивает панель событий и запоминает состояние', async () => {
    const wrapper = mount(AppLayout, {
      slots: {
        default: '<div>page</div>',
        context: '<div data-testid="context-slot">ctx</div>',
      },
      global: {
        mocks: {
          $page: { url: '/dashboard' },
        },
      },
      attachTo: document.body,
    })

    await nextTick()

    const rail = wrapper.get('[data-testid="events-rail"]')
    expect(rail.classes()).toContain('w-80')
    expect(wrapper.find('[data-testid="favorites"]').exists()).toBe(true)

    await wrapper.get('[data-testid="events-rail-toggle"]').trigger('click')
    await nextTick()

    expect(rail.classes()).toContain('w-12')
    expect(wrapper.find('[data-testid="favorites"]').exists()).toBe(false)
    expect(localStorage.getItem('events-rail-collapsed')).toBe('true')
    expect(wrapper.get('[data-testid="events-rail-toggle"]').attributes('aria-expanded')).toBe('false')

    wrapper.unmount()
  })

  it('восстанавливает свёрнутую панель событий из localStorage', async () => {
    localStorage.setItem('events-rail-collapsed', 'true')

    const wrapper = mount(AppLayout, {
      slots: { default: '<div>page</div>' },
      global: {
        mocks: {
          $page: { url: '/dashboard' },
        },
      },
      attachTo: document.body,
    })

    await nextTick()

    expect(wrapper.get('[data-testid="events-rail"]').classes()).toContain('w-12')
    expect(wrapper.find('[data-testid="favorites"]').exists()).toBe(false)

    wrapper.unmount()
  })
})
