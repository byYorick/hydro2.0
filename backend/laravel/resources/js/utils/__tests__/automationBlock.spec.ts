import { describe, expect, it } from 'vitest'
import {
  POLICY_MANAGED_CODES,
  PROCESS_STOPPING_BADGE_LABEL,
  PROCESS_STOPPING_SECTION_TITLE,
  SAFETY_CRITICAL_CODES,
  alertProcessStoppingKind,
  isProcessStoppingCode,
  isSafetyCriticalCode,
} from '@/utils/automationBlock'

describe('automationBlock process-stopping helpers', () => {
  it('recognizes safety-critical hardware codes', () => {
    expect(SAFETY_CRITICAL_CODES).toContain('biz_no_flow')
    expect(isSafetyCriticalCode(' BIZ_OVERCURRENT ')).toBe(true)
    expect(isSafetyCriticalCode('biz_flow_stop_failed_hardware_may_be_active')).toBe(true)
    expect(isSafetyCriticalCode('biz_ec_correction_no_effect')).toBe(false)
    expect(isSafetyCriticalCode(null)).toBe(false)
  })

  it('combines policy-managed and safety-critical codes', () => {
    expect(isProcessStoppingCode('biz_ae3_task_failed')).toBe(true)
    expect(isProcessStoppingCode('biz_pump_stuck_on')).toBe(true)
    expect(isProcessStoppingCode('biz_temp_high')).toBe(false)
    expect(isProcessStoppingCode(undefined)).toBe(false)
  })

  it('returns the UI process-stopping kind for code or alert', () => {
    expect(alertProcessStoppingKind({ code: 'biz_correction_exhausted' })).toBe('automation_block')
    expect(alertProcessStoppingKind('biz_zone_recipe_phase_targets_missing')).toBe('automation_block')
    expect(alertProcessStoppingKind({ code: 'biz_dry_run' })).toBe('safety')
    expect(alertProcessStoppingKind('biz_overcurrent')).toBe('safety')
    expect(alertProcessStoppingKind({ code: 'biz_temp_high' })).toBeNull()
  })

  it('prefers automation_block over safety when both match', () => {
    expect(POLICY_MANAGED_CODES.length).toBeGreaterThan(0)
    expect(alertProcessStoppingKind(POLICY_MANAGED_CODES[0])).toBe('automation_block')
  })

  it('exposes canonical process-stopping UI labels', () => {
    expect(PROCESS_STOPPING_SECTION_TITLE.automation_block).toBe('Блокируют автоматику')
    expect(PROCESS_STOPPING_SECTION_TITLE.safety).toBe('Останавливают железо')
    expect(PROCESS_STOPPING_SECTION_TITLE.other_active).toBe('Остальные активные')
    expect(PROCESS_STOPPING_SECTION_TITLE.other).toBe('Остальные')
    expect(PROCESS_STOPPING_SECTION_TITLE.resolved).toBe('Решённые')
    expect(PROCESS_STOPPING_BADGE_LABEL.automation_block).toBe('Автоматика')
    expect(PROCESS_STOPPING_BADGE_LABEL.safety).toBe('Железо')
  })
})
