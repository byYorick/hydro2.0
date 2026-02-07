import { describe, expect, it } from 'vitest'
import {
  formatCurrency,
  formatIrrigationInterval,
  formatRange,
  formatTargetRange,
  hasPhaseTargets,
  hasTargetValue,
} from '../plantDisplay'

describe('plantDisplay utils', () => {
  it('formatRange корректно форматирует интервалы', () => {
    expect(formatRange(undefined)).toBe('—')
    expect(formatRange({ min: 1, max: 3 })).toBe('1 – 3')
    expect(formatRange({ min: 2 })).toBe('от 2')
    expect(formatRange({ max: 5 })).toBe('до 5')
  })

  it('formatCurrency и formatTargetRange работают с edge-cases', () => {
    expect(formatCurrency(null)).toBe('—')
    expect(formatCurrency(100, 'RUB')).toContain('100')
    expect(formatTargetRange(null)).toBe('-')
    expect(formatTargetRange({ min: 1.2, max: 2.4 })).toBe('1.2–2.4')
  })

  it('hasTargetValue/hasPhaseTargets и formatIrrigationInterval', () => {
    expect(hasTargetValue({ min: 1 })).toBe(true)
    expect(hasTargetValue({})).toBe(false)
    expect(hasPhaseTargets({ ph: { min: 5.5 } })).toBe(true)
    expect(hasPhaseTargets({ ph: {} })).toBe(false)
    expect(formatIrrigationInterval(45)).toBe('45 сек')
    expect(formatIrrigationInterval(120)).toBe('2 мин')
  })
})
