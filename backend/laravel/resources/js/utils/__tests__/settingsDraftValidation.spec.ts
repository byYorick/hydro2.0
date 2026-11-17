import { describe, expect, it } from 'vitest'
import { isSettingsFieldDirty, normalizeSettingsFieldValue, settingsFieldError } from '../settingsDraft'
import type { SystemSettingsField } from '@/types/SystemSettings'

const field: SystemSettingsField = { path: 'attempts', label: 'Число попыток', description: '', type: 'integer', min: 0, max: 10 }

describe('system settings draft validation', () => {
  it.each(['', ' ', undefined, false, '1.5', Number.NaN])('rejects a missing or noninteger count without converting it: %s', value => {
    expect(settingsFieldError(field, value)).not.toBeNull()
    expect(() => normalizeSettingsFieldValue(field, value)).toThrow()
  })
  it('distinguishes a real zero from an empty value and equivalent numeric text', () => {
    expect(normalizeSettingsFieldValue(field, '0')).toBe(0)
    expect(isSettingsFieldDirty(field, '4.0', 4)).toBe(false)
    expect(isSettingsFieldDirty(field, '', 0)).toBe(true)
  })
  it('validates named choices and clock fields before submission', () => {
    const choice = { ...field, type: 'string' as const, options: ['task', 'smart_soil_v1'] }
    expect(settingsFieldError(choice, 'smart_typo')).not.toBeNull()
    expect(settingsFieldError({ ...choice, path: 'start_hhmm', options: undefined }, '25:00')).not.toBeNull()
  })
})
