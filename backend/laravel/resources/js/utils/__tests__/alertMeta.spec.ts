import { describe, expect, it } from 'vitest'
import {
  alertSeveritySortWeight,
  resolveEffectiveAlertSeverity,
  sortAlertsBySeverityAndCreatedAt,
} from '@/utils/alertMeta'
import type { Alert } from '@/types/Alert'

function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 1,
    type: 'TEST',
    code: 'biz_temp_high',
    status: 'active',
    created_at: '2026-03-29T08:00:00Z',
    ...overrides,
  }
}

describe('alertMeta severity helpers', () => {
  it('resolveEffectiveAlertSeverity prefers alert.severity over catalog fallback', () => {
    expect(resolveEffectiveAlertSeverity(makeAlert({ severity: 'warning' }))).toBe('warning')
    expect(resolveEffectiveAlertSeverity(makeAlert({
      code: 'biz_temp_high',
      details: { severity: 'critical' },
    }))).toBe('critical')
  })

  it('sortAlertsBySeverityAndCreatedAt orders by severity then newest created_at', () => {
    const sorted = sortAlertsBySeverityAndCreatedAt([
      makeAlert({ id: 1, severity: 'warning', created_at: '2026-03-29T10:00:00Z' }),
      makeAlert({ id: 2, severity: 'critical', created_at: '2026-03-29T08:00:00Z' }),
      makeAlert({ id: 3, severity: 'critical', created_at: '2026-03-29T12:00:00Z' }),
      makeAlert({ id: 4, severity: 'error', created_at: '2026-03-29T11:00:00Z' }),
    ])

    expect(sorted.map((alert) => alert.id)).toEqual([3, 2, 4, 1])
    expect(alertSeveritySortWeight(makeAlert({ severity: 'critical' }))).toBe(4)
    expect(alertSeveritySortWeight(makeAlert({ severity: 'info' }))).toBe(1)
  })
})
