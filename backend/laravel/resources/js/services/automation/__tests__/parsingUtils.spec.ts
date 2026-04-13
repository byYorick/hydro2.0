import { describe, expect, it } from 'vitest'
import { clamp, isValidHHMM, toFiniteNumber } from '@/services/automation/parsingUtils'

describe('parsingUtils.clamp', () => {
  it('возвращает значение в диапазоне без изменений', () => {
    expect(clamp(5, 0, 10)).toBe(5)
  })

  it('обрезает сверху', () => {
    expect(clamp(15, 0, 10)).toBe(10)
  })

  it('обрезает снизу', () => {
    expect(clamp(-5, 0, 10)).toBe(0)
  })

  it('работает для отрицательных диапазонов', () => {
    expect(clamp(0, -10, -1)).toBe(-1)
  })
})

describe('parsingUtils.toFiniteNumber', () => {
  it('возвращает финитное число как есть', () => {
    expect(toFiniteNumber(42)).toBe(42)
    expect(toFiniteNumber(0)).toBe(0)
    expect(toFiniteNumber(-3.14)).toBe(-3.14)
  })

  it('парсит число из строки', () => {
    expect(toFiniteNumber('7.5')).toBe(7.5)
    expect(toFiniteNumber('0')).toBe(0)
  })

  it('возвращает null для NaN и Infinity', () => {
    expect(toFiniteNumber(NaN)).toBeNull()
    expect(toFiniteNumber(Infinity)).toBeNull()
    expect(toFiniteNumber(-Infinity)).toBeNull()
  })

  it('возвращает null для пустой строки или пробелов', () => {
    expect(toFiniteNumber('')).toBeNull()
    expect(toFiniteNumber('   ')).toBeNull()
  })

  it('возвращает null для невалидной строки', () => {
    expect(toFiniteNumber('abc')).toBeNull()
    expect(toFiniteNumber('1.2.3')).toBeNull()
  })

  it('возвращает null для null/undefined/boolean/object', () => {
    expect(toFiniteNumber(null)).toBeNull()
    expect(toFiniteNumber(undefined)).toBeNull()
    expect(toFiniteNumber(true)).toBeNull()
    expect(toFiniteNumber({})).toBeNull()
  })
})

describe('parsingUtils.isValidHHMM', () => {
  it('принимает валидные значения', () => {
    expect(isValidHHMM('00:00')).toBe(true)
    expect(isValidHHMM('06:30')).toBe(true)
    expect(isValidHHMM('23:59')).toBe(true)
  })

  it('отклоняет значения вне диапазона часов/минут', () => {
    expect(isValidHHMM('24:00')).toBe(false)
    expect(isValidHHMM('12:60')).toBe(false)
  })

  it('требует двузначный формат', () => {
    expect(isValidHHMM('6:30')).toBe(false)
    expect(isValidHHMM('06:3')).toBe(false)
  })

  it('отклоняет произвольный текст', () => {
    expect(isValidHHMM('')).toBe(false)
    expect(isValidHHMM('abc')).toBe(false)
    expect(isValidHHMM('12-30')).toBe(false)
  })
})
