import { describe, expect, it } from 'vitest'
import {
  canCreateGreenhouse,
  canSelectGreenhouse,
} from '@/composables/setupWizardGreenhouseCommands'
import {
  canCreateZone,
  canSelectZone,
} from '@/composables/setupWizardZoneCommands'

describe('setupWizardGreenhouseCommands preconditions', () => {
  it('canCreateGreenhouse проверяет права и непустое имя', () => {
    expect(canCreateGreenhouse(true, 'GH Main')).toBe(true)
    expect(canCreateGreenhouse(true, '   ')).toBe(false)
    expect(canCreateGreenhouse(false, 'GH Main')).toBe(false)
  })

  it('canSelectGreenhouse проверяет права и наличие id', () => {
    expect(canSelectGreenhouse(true, 10)).toBe(true)
    expect(canSelectGreenhouse(true, null)).toBe(false)
    expect(canSelectGreenhouse(false, 10)).toBe(false)
  })
})

describe('setupWizardZoneCommands preconditions', () => {
  it('canCreateZone проверяет права, greenhouseId и непустое имя зоны', () => {
    expect(canCreateZone(true, 5, 'Zone A')).toBe(true)
    expect(canCreateZone(true, null, 'Zone A')).toBe(false)
    expect(canCreateZone(true, 5, '   ')).toBe(false)
    expect(canCreateZone(false, 5, 'Zone A')).toBe(false)
  })

  it('canSelectZone проверяет права и наличие zone id', () => {
    expect(canSelectZone(true, 20)).toBe(true)
    expect(canSelectZone(true, null)).toBe(false)
    expect(canSelectZone(false, 20)).toBe(false)
  })
})
