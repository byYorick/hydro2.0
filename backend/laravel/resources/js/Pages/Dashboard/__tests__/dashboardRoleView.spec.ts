import { describe, expect, it } from 'vitest'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import { buildEngineeringIssues, zoneNeedsAgronomyDecision, zonePhEcCorridor } from '../dashboardRoleView'

const now = Date.parse('2026-11-08T12:00:00Z')
function zone(override: Partial<UnifiedZone> = {}): UnifiedZone {
  return {
    id: 1, name: 'Зона A', status: 'RUNNING', greenhouse: null, crop: null, recipe: null, plant: null, cycle: null,
    alerts_count: 0, alerts_preview: [], devices: { total: 3, online: 2 },
    telemetry: { ph: 5.8, ec: 1.6, temperature: null, humidity: null, co2: null, updated_at: new Date(now - 15_000).toISOString() },
    targets: { ph: { min: 5.6, max: 6.2 }, ec: { min: 1.4, max: 1.8 }, temperature: null },
    ...override,
  }
}

describe('Ролевая оценка данных обзора', () => {
  it('не подменяет отсутствующие измерения статусом процесса', () => {
    const current = zone()
    current.telemetry.ph = null
    current.telemetry.ec = null
    for (const status of ['RUNNING', 'OK', 'WARNING', 'ALARM']) {
      expect(zonePhEcCorridor({ ...current, status }, now)).toBe('unknown')
    }
  })
  it('не даёт зелёную оценку при пропуске обязательного показателя', () => {
    const current = zone()
    current.telemetry.ec = null
    expect(zonePhEcCorridor(current, now)).toBe('unknown')
    current.targets.ec = null
    expect(zonePhEcCorridor(current, now)).toBe('in')
    current.targets.ph = null
    expect(zonePhEcCorridor(current, now)).toBe('unknown')
  })
  it('отличает свежие данные, устаревшие данные и неверное время', () => {
    const current = zone()
    expect(zonePhEcCorridor(current, now)).toBe('in')
    for (const updated_at of [null, 'invalid', new Date(now - 300_001).toISOString(), new Date(now + 60_000).toISOString()]) {
      expect(zonePhEcCorridor({ ...current, telemetry: { ...current.telemetry, updated_at } }, now)).toBe('unknown')
    }
  })
  it('не принимает бесконечные значения и перевёрнутые диапазоны', () => {
    const current = zone()
    current.telemetry.ph = Infinity
    expect(zonePhEcCorridor(current, now)).toBe('unknown')
    current.telemetry.ph = 5.8
    current.targets.ph = { min: 6.5, max: 5.5 }
    expect(zonePhEcCorridor(current, now)).toBe('unknown')
  })
  it('отделяет отклонение раствора от блокировки процесса', () => {
    const current = zone()
    current.telemetry.ec = 1.95
    expect(zonePhEcCorridor(current, now)).toBe('out')
    expect(zoneNeedsAgronomyDecision(current, now)).toBe(true)
    current.telemetry.ec = 1.6
    current.automation_block = { blocked: true, reason_code: null, severity: 'critical', message: 'Полив остановлен', since: null, alert_id: null, alerts_count: 1 }
    expect(zonePhEcCorridor(current, now)).toBe('in')
    expect(zoneNeedsAgronomyDecision(current, now)).toBe(true)
  })
  it('считает отключённые узлы из количества работающих', () => {
    expect(buildEngineeringIssues([zone()])[0].reasons).toContain('Узлы не на связи: 1 из 3')
    expect(buildEngineeringIssues([zone({ devices: { online: 0, total: 0 } })])).toEqual([])
  })
})
