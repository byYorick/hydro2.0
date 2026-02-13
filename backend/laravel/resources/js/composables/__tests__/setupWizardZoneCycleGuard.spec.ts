import { describe, expect, it } from 'vitest'
import {
  extractZoneActiveCycleStatus,
  isZoneCycleBlocking,
  zoneCycleStatusLabel,
} from '@/composables/setupWizardZoneCycleGuard'

describe('setupWizardZoneCycleGuard', () => {
  it('extracts active cycle status from snake_case relation', () => {
    const status = extractZoneActiveCycleStatus({
      id: 10,
      active_grow_cycle: {
        id: 55,
        status: 'running',
      },
    })

    expect(status).toBe('RUNNING')
  })

  it('extracts active cycle status from camelCase relation', () => {
    const status = extractZoneActiveCycleStatus({
      id: 10,
      activeGrowCycle: {
        id: 55,
        status: 'paused',
      },
    })

    expect(status).toBe('PAUSED')
  })

  it('returns null when zone has no active cycle relation', () => {
    expect(extractZoneActiveCycleStatus({ id: 10 })).toBeNull()
  })

  it('marks only planned/running/paused as blocking', () => {
    expect(isZoneCycleBlocking('PLANNED')).toBe(true)
    expect(isZoneCycleBlocking('RUNNING')).toBe(true)
    expect(isZoneCycleBlocking('PAUSED')).toBe(true)
    expect(isZoneCycleBlocking('HARVESTED')).toBe(false)
    expect(isZoneCycleBlocking('ABORTED')).toBe(false)
    expect(isZoneCycleBlocking(null)).toBe(false)
  })

  it('returns readable russian label for statuses', () => {
    expect(zoneCycleStatusLabel('planned')).toBe('PLANNED (запланирован)')
    expect(zoneCycleStatusLabel('running')).toBe('RUNNING (выполняется)')
    expect(zoneCycleStatusLabel('paused')).toBe('PAUSED (на паузе)')
    expect(zoneCycleStatusLabel('harvested')).toBe('HARVESTED')
  })
})
