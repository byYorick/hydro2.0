import { describe, expect, it } from 'vitest'
import { resolveAlertPreviewSeverity } from '../alertPreviewSeverity'

describe('resolveAlertPreviewSeverity', () => {
  it('использует backend severity при известных значениях', () => {
    expect(resolveAlertPreviewSeverity('critical', 'anything')).toBe('critical')
    expect(resolveAlertPreviewSeverity('error', 'task_warning')).toBe('error')
    expect(resolveAlertPreviewSeverity('warning', 'task_failed')).toBe('warning')
    expect(resolveAlertPreviewSeverity('info', 'task_failed')).toBe('info')
    expect(resolveAlertPreviewSeverity('CRITICAL', null)).toBe('critical')
  })

  it('fallback на type, если severity отсутствует или неизвестна', () => {
    expect(resolveAlertPreviewSeverity(null, 'task_failed')).toBe('error')
    expect(resolveAlertPreviewSeverity(undefined, 'critical_alarm')).toBe('critical')
    expect(resolveAlertPreviewSeverity('other', 'sensor_warn')).toBe('warning')
    expect(resolveAlertPreviewSeverity('', 'info_notice')).toBe('info')
    expect(resolveAlertPreviewSeverity(null, 'unknown_event')).toBe('warning')
  })
})
