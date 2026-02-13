import { describe, expect, it } from 'vitest'
import {
  isValidReconciliationData,
  isValidSnapshot,
} from '../reconciliation'

describe('reconciliation type guards', () => {
  it('isValidSnapshot возвращает true для валидного snapshot', () => {
    const validSnapshot = {
      snapshot_id: 'snap-1',
      server_ts: 123456,
      zone_id: 7,
      telemetry: {},
      active_alerts: [],
      recent_commands: [],
      nodes: [],
    }

    expect(isValidSnapshot(validSnapshot)).toBe(true)
  })

  it('isValidSnapshot возвращает false для невалидного snapshot', () => {
    expect(isValidSnapshot(null)).toBe(false)
    expect(isValidSnapshot({})).toBe(false)
    expect(isValidSnapshot({
      snapshot_id: 'snap-1',
      server_ts: 'bad',
      zone_id: 7,
      telemetry: {},
      active_alerts: [],
      recent_commands: [],
      nodes: [],
    })).toBe(false)
  })

  it('isValidReconciliationData валидирует optional-массивы', () => {
    expect(isValidReconciliationData({})).toBe(true)
    expect(isValidReconciliationData({ telemetry: [], commands: [], alerts: [] })).toBe(true)
    expect(isValidReconciliationData({ telemetry: 'bad' })).toBe(false)
    expect(isValidReconciliationData(null)).toBe(false)
  })
})
