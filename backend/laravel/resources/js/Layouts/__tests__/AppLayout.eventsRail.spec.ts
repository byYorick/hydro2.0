import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import AppLayout from '../AppLayout.vue'

let page: { url: string; props: { auth: { user: { id: number; name: string } } } }
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => page,
  Link: { name: 'Link', template: '<a><slot /></a>' },
}))

vi.mock('@/composables/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: vi.fn(),
}))

vi.mock('@/Components/CommandPalette.vue', () => ({
  default: { name: 'CommandPalette', template: '<div />' },
}))
vi.mock('@/Components/RoleBasedNavigation.vue', () => ({
  default: { name: 'RoleBasedNavigation', template: '<nav><a href="/zones">Зоны</a></nav>' },
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
  default: { name: 'MobileNavigation', emits: ['open-menu'], template: '<button aria-label="Ещё разделы" @click="$emit(\'open-menu\')">Ещё</button>' },
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

describe('AppLayout.vue — context panels', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    localStorage.clear()
    page = reactive({ url: '/', props: { auth: { user: { id: 1, name: 'Test' } } } })
  })

  afterEach(() => {
    wrapper?.unmount()
    localStorage.clear()
    document.body.innerHTML = ''
  })

  function renderLayout() {
    wrapper = mount(AppLayout, {
      slots: {
        default: '<div>page</div>',
        context: '<div data-testid="context-slot">ctx</div>',
      },
      attachTo: document.body,
    })
    return wrapper
  }

  it('освобождает страницу по умолчанию и открывает события по запросу', async () => {
    renderLayout()
    await nextTick()
    expect(document.querySelector('[data-testid="events-rail"]')).toBeNull()
    const toggle = wrapper.get('[data-testid="events-rail-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    await nextTick()

    const rail = document.querySelector('[data-testid="events-rail"]')
    expect(rail?.getAttribute('role')).toBe('dialog')
    expect(rail?.getAttribute('aria-modal')).toBe('true')
    expect(rail?.querySelector('[data-testid="favorites"]')).not.toBeNull()
    expect(rail?.querySelector('[data-testid="history"]')).not.toBeNull()
    expect(rail?.querySelector('[data-testid="context-slot"]')?.textContent).toBe('ctx')
    expect(localStorage.getItem('events-rail-collapsed')).toBe('false')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(document.querySelector('[data-testid="events-rail"]')).toBeNull()
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(localStorage.getItem('events-rail-collapsed')).toBe('true')
  })

  it.each(['true', 'false'])('сохраняет явный выбор панели: collapsed=%s', async (stored) => {
    localStorage.setItem('events-rail-collapsed', stored)
    renderLayout()
    await nextTick()
    expect(document.querySelector('[data-testid="events-rail"]') !== null).toBe(stored === 'false')
  })

  it('закрывает открытые панели при переходе на другую страницу', async () => {
    renderLayout()
    await wrapper.get('[data-testid="events-rail-toggle"]').trigger('click')
    expect(document.querySelector('[data-testid="events-rail"]')).not.toBeNull()
    page.url = '/zones'
    await nextTick()
    expect(document.querySelector('[data-testid="events-rail"]')).toBeNull()
  })

  it('показывает все ролевые разделы из мобильного Ещё и закрывает меню после выбора', async () => {
    renderLayout()
    await wrapper.get('button[aria-label="Ещё разделы"]').trigger('click')
    const menu = document.getElementById('mobile-nav')
    expect(menu?.getAttribute('role')).toBe('dialog')
    const link = menu?.querySelector('a') as HTMLAnchorElement
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    await nextTick()
    expect(document.getElementById('mobile-nav')).toBeNull()
  })
})
