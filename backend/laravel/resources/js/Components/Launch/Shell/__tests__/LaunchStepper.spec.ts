import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import LaunchStepper from '../LaunchStepper.vue'
import {
  _resetLaunchPreferencesForTests,
  useLaunchPreferences,
} from '@/composables/useLaunchPreferences'
import type { LaunchStep, StepCompletion } from '../types'

const steps: LaunchStep[] = [
  { id: 'zone', label: 'Зона', sub: 'теплица' },
  { id: 'recipe', label: 'Рецепт', sub: 'фазы' },
]

function mockMatchMedia(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('LaunchStepper', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders horizontal when stepper=horizontal', async () => {
    mockMatchMedia(true)
    const { setStepper } = useLaunchPreferences()
    setStepper('horizontal')
    const w = mount(LaunchStepper, {
      props: {
        steps,
        active: 0,
        completion: ['current', 'todo'] as StepCompletion[],
      },
    })
    await nextTick()
    expect(w.find('aside').exists()).toBe(false)
  })

  it('renders vertical when stepper=vertical and screen ≥1280px', async () => {
    mockMatchMedia(true)
    const { setStepper } = useLaunchPreferences()
    setStepper('vertical')
    const w = mount(LaunchStepper, {
      props: {
        steps,
        active: 0,
        completion: ['current', 'todo'] as StepCompletion[],
      },
    })
    await nextTick()
    expect(w.find('aside').exists()).toBe(true)
  })

  it('falls back to horizontal on narrow screens even when stepper=vertical', async () => {
    mockMatchMedia(false)
    const { setStepper } = useLaunchPreferences()
    setStepper('vertical')
    const w = mount(LaunchStepper, {
      props: {
        steps,
        active: 0,
        completion: ['current', 'todo'] as StepCompletion[],
      },
    })
    await nextTick()
    expect(w.find('aside').exists()).toBe(false)
  })
})
