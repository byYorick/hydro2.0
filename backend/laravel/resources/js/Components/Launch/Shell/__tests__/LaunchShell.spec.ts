import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LaunchShell from '../LaunchShell.vue'
import {
  _resetLaunchPreferencesForTests,
  useLaunchPreferences,
} from '@/composables/useLaunchPreferences'

vi.mock('../LaunchTopBar.vue', () => ({
  default: { name: 'LaunchTopBar', template: '<div data-test="topbar-stub" />' },
}))

describe('LaunchShell', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  it('applies data-density and data-stepper attributes from preferences', () => {
    const { setDensity, setStepper } = useLaunchPreferences()
    setDensity('comfortable')
    setStepper('vertical')
    const w = mount(LaunchShell)
    const root = w.element as HTMLElement
    expect(root.getAttribute('data-density')).toBe('comfortable')
    expect(root.getAttribute('data-stepper')).toBe('vertical')
  })

  it('renders default slot content', () => {
    const w = mount(LaunchShell, {
      slots: { default: '<div data-test="step-body">шаг</div>' },
    })
    expect(w.find('[data-test="step-body"]').exists()).toBe(true)
    expect(w.text()).toContain('шаг')
  })

  it('renders TopBar by default and supports overriding via slot', () => {
    const w1 = mount(LaunchShell)
    expect(w1.find('[data-test="topbar-stub"]').exists()).toBe(true)

    const w2 = mount(LaunchShell, {
      slots: { topbar: '<header data-test="custom-topbar">CUSTOM</header>' },
    })
    expect(w2.find('[data-test="custom-topbar"]').exists()).toBe(true)
  })
})
