import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import LaunchSettingsPopover from '../LaunchSettingsPopover.vue'
import {
  _resetLaunchPreferencesForTests,
  useLaunchPreferences,
} from '@/composables/useLaunchPreferences'

describe('LaunchSettingsPopover', () => {
  beforeEach(() => {
    localStorage.clear()
    _resetLaunchPreferencesForTests()
  })

  it('renders density / stepper / hints sections', () => {
    const w = mount(LaunchSettingsPopover)
    expect(w.text()).toContain('Плотность')
    expect(w.text()).toContain('Степпер')
    expect(w.text()).toContain('Показывать подсказки')
    expect(w.text()).toContain('Компактная')
    expect(w.text()).toContain('Просторная')
    expect(w.text()).toContain('Горизонтальный')
    expect(w.text()).toContain('Вертикальный')
  })

  it('updates density on click', async () => {
    const { density } = useLaunchPreferences()
    expect(density.value).toBe('compact')
    const w = mount(LaunchSettingsPopover)
    const comfortableBtn = w
      .findAll('button')
      .find((b) => b.text() === 'Просторная')!
    await comfortableBtn.trigger('click')
    expect(density.value).toBe('comfortable')
  })

  it('updates stepper on click and shows wide-screen hint when vertical', async () => {
    const w = mount(LaunchSettingsPopover)
    expect(w.text()).not.toContain('≥1280')
    const verticalBtn = w
      .findAll('button')
      .find((b) => b.text() === 'Вертикальный')!
    await verticalBtn.trigger('click')
    expect(useLaunchPreferences().stepper.value).toBe('vertical')
    expect(w.text()).toContain('≥1280')
  })

  it('toggles showHints via checkbox', async () => {
    const { showHints } = useLaunchPreferences()
    expect(showHints.value).toBe(true)
    const w = mount(LaunchSettingsPopover)
    const checkbox = w.find('input[type="checkbox"]')
    await checkbox.setValue(false)
    expect(showHints.value).toBe(false)
  })
})
