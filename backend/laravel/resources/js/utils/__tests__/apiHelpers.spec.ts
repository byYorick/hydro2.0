import { describe, expect, it } from 'vitest'
import {
  extractData,
  extractDataWithFallback,
  normalizeResponse,
} from '../apiHelpers'

describe('apiHelpers', () => {
  it('extractData поддерживает прямой, одинарный и двойной envelope', () => {
    expect(extractData<{ a: number }>({ a: 1 })).toEqual({ a: 1 })
    expect(extractData<{ a: number }>({ data: { a: 2 } })).toEqual({ a: 2 })
    expect(extractData<{ a: number }>({ data: { data: { a: 3 } } })).toEqual({ a: 3 })
  })

  it('extractData возвращает null для пустого ответа', () => {
    expect(extractData(null)).toBeNull()
    expect(extractData(undefined)).toBeNull()
  })

  it('normalizeResponse валидирует expectedType', () => {
    expect(normalizeResponse<number[]>({ data: [1, 2] }, 'array')).toEqual([1, 2])
    expect(() => normalizeResponse({ data: { a: 1 } }, 'array')).toThrow('Expected array')
    expect(() => normalizeResponse({ data: [1] }, 'object')).toThrow('Expected object')
  })

  it('extractDataWithFallback использует fallback только при null/undefined', () => {
    expect(extractDataWithFallback<number>(undefined, 10)).toBe(10)
    expect(extractDataWithFallback<number>(null, 10)).toBe(10)
    expect(extractDataWithFallback<number>({ data: 5 }, 10)).toBe(5)
  })
})
