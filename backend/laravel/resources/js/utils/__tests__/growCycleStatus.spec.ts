import { describe, it, expect } from 'vitest'
import { getCycleStatusLabel, getCycleStatusVariant } from '../growCycleStatus'

describe('growCycleStatus', () => {
  it('returns default labels for known statuses', () => {
    expect(getCycleStatusLabel('RUNNING')).toBe('Запущен')
    expect(getCycleStatusLabel('PAUSED')).toBe('Приостановлен')
    expect(getCycleStatusLabel('PLANNED')).toBe('Запланирован')
  })

  it('supports short labels', () => {
    expect(getCycleStatusLabel('RUNNING', 'short')).toBe('Активен')
    expect(getCycleStatusLabel('PAUSED', 'short')).toBe('Пауза')
  })

  it('supports sentence labels', () => {
    expect(getCycleStatusLabel('RUNNING', 'sentence')).toBe('Цикл активен')
    expect(getCycleStatusLabel('PLANNED', 'sentence')).toBe('Цикл запланирован')
  })

  it('returns status for unknown labels', () => {
    expect(getCycleStatusLabel('UNKNOWN')).toBe('UNKNOWN')
  })

  it('returns variants by style', () => {
    expect(getCycleStatusVariant('RUNNING')).toBe('success')
    expect(getCycleStatusVariant('PLANNED')).toBe('neutral')
    expect(getCycleStatusVariant('PLANNED', 'center')).toBe('info')
  })
})
