import { describe, it, expect } from 'vitest'
import {
  normalizeDurationHours,
  calculateProgressBetween,
  calculateProgressFromDuration,
} from '../growCycleProgress'

describe('growCycleProgress', () => {
  it('normalizes duration in hours', () => {
    expect(normalizeDurationHours(12, null)).toBe(12)
    expect(normalizeDurationHours(null, 2)).toBe(48)
    expect(normalizeDurationHours(null, null)).toBeNull()
  })

  it('calculates progress between two dates', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    const end = new Date('2025-01-01T10:00:00Z')
    const now = new Date('2025-01-01T05:00:00Z')

    expect(calculateProgressBetween(start, end, now)).toBe(50)
    expect(calculateProgressBetween(start, end, new Date('2025-01-01T00:00:00Z'))).toBe(0)
    expect(calculateProgressBetween(start, end, new Date('2025-01-01T11:00:00Z'))).toBe(100)
  })

  it('returns null when progress cannot be calculated', () => {
    expect(calculateProgressBetween(null, null)).toBeNull()
    expect(calculateProgressBetween('bad', 'also-bad')).toBeNull()
  })

  it('calculates progress from duration', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    const now = new Date('2025-01-01T02:30:00Z')

    expect(calculateProgressFromDuration(start, 10, null, now)).toBe(25)
    expect(calculateProgressFromDuration(start, null, 1, now)).toBeCloseTo(10.4167, 3)
  })

  it('returns null when duration data is missing', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    expect(calculateProgressFromDuration(start, null, null)).toBeNull()
  })
})
