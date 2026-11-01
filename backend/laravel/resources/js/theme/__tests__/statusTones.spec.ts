import { describe, expect, it } from 'vitest'
import {
  badgeVariantClass,
  canonicalStatusTone,
  chipToneClass,
  statusPillClass,
} from '@/theme/statusTones'

describe('statusTones', () => {
  it('сводит legacy-имена к одному статусу', () => {
    expect(canonicalStatusTone('growth')).toBe('ok')
    expect(canonicalStatusTone('success')).toBe('ok')
    expect(canonicalStatusTone('warn')).toBe('warning')
    expect(canonicalStatusTone('alert')).toBe('critical')
    expect(canonicalStatusTone('danger')).toBe('critical')
    expect(canonicalStatusTone('brand')).toBe('info')
    expect(canonicalStatusTone('offline')).toBe('offline')
    expect(canonicalStatusTone(undefined)).toBe('neutral')
  })

  it('оставляет Hydroflow-классы Chip для старых тонов', () => {
    expect(chipToneClass('growth')).toContain('bg-growth-soft')
    expect(chipToneClass('warn')).toContain('text-warn')
    expect(chipToneClass('alert')).toContain('bg-alert-soft')
    expect(chipToneClass('brand')).toContain('text-brand-ink')
    expect(chipToneClass('neutral')).toContain('bg-[var(--bg-elevated)]')
  })

  it('красит новые тона общими классами', () => {
    expect(chipToneClass('ok')).toBe('tone-ok')
    expect(chipToneClass('offline')).toBe('tone-offline')
    expect(statusPillClass('critical')).toBe('status-chip--alarm')
    expect(statusPillClass('offline')).toBe('status-chip--offline')
    expect(badgeVariantClass('success')).toBe('badge--success')
    expect(badgeVariantClass('offline')).toBe('badge--offline')
    expect(badgeVariantClass('critical')).toBe('badge--critical')
  })
})
