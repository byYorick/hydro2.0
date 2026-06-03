import { describe, expect, it } from 'vitest'
import {
  controlModeDisabledReason,
  isControlModeTransitionAllowed,
} from '@/utils/zoneAutomationControlMode'

describe('zoneAutomationControlMode', () => {
  it('разрешает agronomist любые переходы', () => {
    expect(isControlModeTransitionAllowed('agronomist', 'auto', 'manual')).toBe(true)
    expect(isControlModeTransitionAllowed('agronomist', 'manual', 'semi')).toBe(true)
  })

  it('operator только auto|semi → manual', () => {
    expect(isControlModeTransitionAllowed('operator', 'semi', 'manual')).toBe(true)
    expect(isControlModeTransitionAllowed('operator', 'manual', 'auto')).toBe(false)
    expect(controlModeDisabledReason('operator', 'manual', 'auto')).toContain('Оператор')
  })

  it('viewer не может менять режим', () => {
    expect(isControlModeTransitionAllowed('viewer', 'auto', 'semi')).toBe(false)
  })
})
