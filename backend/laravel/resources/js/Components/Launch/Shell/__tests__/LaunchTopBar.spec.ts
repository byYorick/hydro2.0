import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

vi.mock('@inertiajs/vue3', () => ({
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href"><slot /></a>',
  },
}))

vi.mock('@/composables/useServiceHealth', () => ({
  useServiceHealth: () => ({
    query: {
      isLoading: ref(false),
      data: ref(null),
      isError: ref(false),
    },
    pills: computed(() => [
      { key: 'automation_engine', label: 'AE3', status: 'online' },
      { key: 'history_logger', label: 'history-logger', status: 'degraded' },
      { key: 'mqtt', label: 'mqtt-bridge', status: 'offline' },
    ]),
  }),
}))

import LaunchTopBar from '../LaunchTopBar.vue'
import { _resetLaunchPreferencesForTests } from '@/composables/useLaunchPreferences'

// Ziggy `route()` helper в продакшне регистрируется через VueApp use(ZiggyVue);
// в тестах подставляем заглушку через global.mocks.
const routeMock = (name: string) => `/${name}`

const mountTopBar = (slots?: Record<string, string>) =>
  mount(LaunchTopBar, {
    slots,
    global: { mocks: { route: routeMock } },
  })

describe('LaunchTopBar', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  it('renders Hydroflow logo + version + breadcrumb', () => {
    const w = mountTopBar()
    expect(w.text()).toContain('Hydroflow')
    expect(w.text()).toContain('v2.0·ae3')
    expect(w.text()).toContain('Мастер запуска')
  })

  it('renders 3 service-health pills with labels', () => {
    const w = mountTopBar()
    expect(w.text()).toContain('AE3')
    expect(w.text()).toContain('history-logger')
    expect(w.text()).toContain('mqtt-bridge')
  })

  it('settings popover is hidden by default and toggles on settings click', async () => {
    const w = mountTopBar()
    expect(w.text()).not.toContain('Плотность')
    const settingsBtn = w.find('[aria-label*="настройки"]')
    expect(settingsBtn.exists()).toBe(true)
    await settingsBtn.trigger('click')
    expect(w.text()).toContain('Плотность')
    expect(w.text()).toContain('Степпер')
  })

  it('exposes breadcrumbs slot for override', () => {
    const w = mountTopBar({
      breadcrumbs: '<span data-test="custom-crumbs">CUSTOM</span>',
    })
    expect(w.find('[data-test="custom-crumbs"]').exists()).toBe(true)
    expect(w.text()).not.toContain('Dashboard')
  })

  it('aria-expanded on settings button reflects open state', async () => {
    const w = mountTopBar()
    const settingsBtn = w.find('[aria-label*="настройки"]')
    expect(settingsBtn.attributes('aria-expanded')).toBe('false')
    await settingsBtn.trigger('click')
    expect(settingsBtn.attributes('aria-expanded')).toBe('true')
  })
})
