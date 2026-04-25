import { describe, expect, it } from 'vitest'
import { mapServiceStatus } from '../useServiceHealth'

describe('useServiceHealth.mapServiceStatus', () => {
  it("maps 'ok' → online", () => {
    expect(mapServiceStatus('ok')).toBe('online')
  })

  it("maps 'fail' → offline", () => {
    expect(mapServiceStatus('fail')).toBe('offline')
  })

  it("maps 'unknown' → unknown", () => {
    expect(mapServiceStatus('unknown')).toBe('unknown')
  })

  it('maps undefined / null → unknown', () => {
    expect(mapServiceStatus(undefined)).toBe('unknown')
    expect(mapServiceStatus(null)).toBe('unknown')
  })

  it('maps any other string → degraded', () => {
    expect(mapServiceStatus('warn')).toBe('degraded')
    expect(mapServiceStatus('partial')).toBe('degraded')
  })
})
