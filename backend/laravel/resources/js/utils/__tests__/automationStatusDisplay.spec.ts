import { describe, expect, it } from 'vitest'
import {
  buildProgressSummary,
  computeDisplayElapsedSec,
  formatAutomationDuration,
  formatAutomationElapsedLabel,
  formatAutomationRemainingLabel,
  resolveStageHeadline,
  shouldShowProgressPercent,
} from '@/utils/automationStatusDisplay'
import type { AutomationState } from '@/types/Automation'
import { hasExplicitControlMode } from '@/composables/zoneAutomationUtils'

describe('automationStatusDisplay', () => {
  it('hasExplicitControlMode отличает отсутствие поля от auto', () => {
    expect(hasExplicitControlMode(undefined)).toBe(false)
    expect(hasExplicitControlMode('')).toBe(false)
    expect(hasExplicitControlMode('semi')).toBe(true)
    expect(hasExplicitControlMode('auto')).toBe(true)
  })
  it('не показывает 00:00 при нулевом elapsed', () => {
    expect(formatAutomationDuration(0)).toBe('')
    expect(buildProgressSummary({
      progressPercent: 0,
      elapsedSec: 0,
      estimatedCompletionSec: null,
      isProcessActive: true,
    })).toBe('Выполняется…')
  })

  it('собирает progress summary без ложного нуля', () => {
    expect(buildProgressSummary({
      progressPercent: 42,
      elapsedSec: 125,
      estimatedCompletionSec: 895,
      isProcessActive: true,
    })).toBe('42% · 02:05 · осталось 14:55')
  })

  it('форматирует подписи прошло/осталось', () => {
    expect(formatAutomationElapsedLabel(125)).toBe('Прошло 02:05')
    expect(formatAutomationRemainingLabel(895)).toBe('осталось 14:55')
  })

  it('предпочитает current_stage_label для заголовка', () => {
    const state = {
      state_label: 'Полив',
      current_stage_label: 'Наполнение раствором',
    } as AutomationState

    expect(resolveStageHeadline(state, 'Ожидание')).toBe('Наполнение раствором')
  })

  it('считает elapsed от stage_entered_at на клиенте', () => {
    const nowMs = Date.parse('2026-06-01T12:02:05.000Z')
    const elapsed = computeDisplayElapsedSec({
      elapsedSec: 0,
      stageEnteredAt: '2026-06-01T12:00:00.000Z',
      servedAt: null,
      nowMs,
    })
    expect(elapsed).toBe(125)
  })

  it('показывает progress bar при активном процессе', () => {
    expect(shouldShowProgressPercent(0, true)).toBe(true)
    expect(shouldShowProgressPercent(0, false)).toBe(false)
  })
})
