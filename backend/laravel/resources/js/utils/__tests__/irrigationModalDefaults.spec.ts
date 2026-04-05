import { describe, it, expect } from 'vitest'
import { pickIrrigationDurationFromTargets } from '../irrigationModalDefaults'

describe('pickIrrigationDurationFromTargets', () => {
  it('reads flat irrigation_duration_sec', () => {
    expect(pickIrrigationDurationFromTargets({ irrigation_duration_sec: 120 })).toBe(120)
  })

  it('reads nested irrigation.duration_sec', () => {
    expect(
      pickIrrigationDurationFromTargets({
        irrigation: { duration_sec: 45 },
      }),
    ).toBe(45)
  })

  it('clamps to 3600', () => {
    expect(pickIrrigationDurationFromTargets({ irrigation_duration_sec: 99999 })).toBe(3600)
  })

  it('returns undefined when missing', () => {
    expect(pickIrrigationDurationFromTargets({})).toBeUndefined()
    expect(pickIrrigationDurationFromTargets(null)).toBeUndefined()
  })
})
