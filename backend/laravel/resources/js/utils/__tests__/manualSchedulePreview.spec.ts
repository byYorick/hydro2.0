import { describe, expect, it } from 'vitest'
import {
  buildManualScheduleSummary,
  collectManualScheduleFormErrors,
  isManualScheduleFormValid,
  previewManualScheduleTriggers,
  MANUAL_SCHEDULE_LIMITS,
} from '@/utils/manualSchedulePreview'
import type { ZoneManualSchedulePayload } from '@/composables/zoneScheduleWorkspaceTypes'

describe('manualSchedulePreview', () => {
  const baseTimeForm: ZoneManualSchedulePayload = {
    task_type: 'irrigation',
    schedule_kind: 'time',
    time_at: '08:00',
    days_of_week: [1, 3, 5],
    payload: { duration_sec: 120 },
    enabled: true,
  }

  it('builds human summary for time schedule', () => {
    const summary = buildManualScheduleSummary(baseTimeForm)
    expect(summary).toContain('Полив')
    expect(summary).toContain('Пн')
    expect(summary).toContain('08:00')
  })

  it('validates time schedule when time_at present', () => {
    expect(isManualScheduleFormValid(baseTimeForm)).toBe(true)
    expect(isManualScheduleFormValid({ ...baseTimeForm, time_at: undefined })).toBe(false)
  })

  it('previews upcoming triggers for interval schedule', () => {
    const form: ZoneManualSchedulePayload = {
      task_type: 'lighting',
      schedule_kind: 'interval',
      interval_sec: 3600,
      days_of_week: [],
      enabled: true,
    }
    const triggers = previewManualScheduleTriggers(form, 3)
    expect(triggers.length).toBeGreaterThan(0)
    expect(triggers[0]?.relativeLabel).toMatch(/через/)
  })

  it('rejects duration below backend minimum', () => {
    const errors = collectManualScheduleFormErrors({
      ...baseTimeForm,
      payload: { duration_sec: 5 },
    })
    expect(errors['payload.duration_sec']?.[0]).toContain(String(MANUAL_SCHEDULE_LIMITS.durationSec.min))
  })

  it('rejects interval above backend maximum', () => {
    const errors = collectManualScheduleFormErrors({
      task_type: 'irrigation',
      schedule_kind: 'interval',
      interval_sec: 90_000,
      enabled: true,
    })
    expect(errors.interval_sec?.[0]).toContain(String(MANUAL_SCHEDULE_LIMITS.intervalSec.max))
  })

  it('requires future run_at when creating once schedule', () => {
    const past = new Date(Date.now() - 3_600_000).toISOString()
    const errors = collectManualScheduleFormErrors(
      {
        task_type: 'lighting',
        schedule_kind: 'once',
        run_at: past,
        enabled: true,
      },
      { isCreate: true },
    )
    expect(errors.run_at?.[0]).toMatch(/будущем/)
  })

  it('rejects non-finite interval values', () => {
    const errors = collectManualScheduleFormErrors({
      task_type: 'irrigation',
      schedule_kind: 'interval',
      interval_sec: Number.NaN,
      enabled: true,
    })
    expect(errors.interval_sec?.[0]).toMatch(/корректный/)
  })

  it('returns no preview triggers when schedule is disabled', () => {
    const triggers = previewManualScheduleTriggers({
      ...baseTimeForm,
      enabled: false,
    })
    expect(triggers).toEqual([])
  })
})
