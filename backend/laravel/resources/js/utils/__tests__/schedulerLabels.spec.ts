import { executionDecisionLabel } from '../schedulerPresentation'
import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'
import { describe, expect, it } from 'vitest'
import { controlModeLabel, decisionLabel, laneLabel, statusLabel, workflowStageLabel } from '../schedulerLabels'
describe('operator scheduler wording', () => {
  it('does not invent automatic control when mode is absent or unknown', () => {
    expect(controlModeLabel(null)).toContain('неизвестен')
    expect(controlModeLabel('future')).toContain('неизвестен')
    expect(controlModeLabel('auto')).toBe('автоматический')
  })
  it('keeps decision admission distinct from execution and unknown state', () => {
    expect(decisionLabel('run', false)).toBe('Полив разрешён')
    expect(decisionLabel('skip', false)).toBe('Полив пропущен')
    expect(statusLabel('future')).toContain('не распознан')
    expect(laneLabel('irrigation_start')).toBe('Полив')
    expect(workflowStageLabel('decision_gate')).toBe('Проверка условий полива')
  })
})

it('does not claim that completed non-irrigation tasks are waiting for a watering decision', () => {
  const run = { task_type: 'lighting_tick', status: 'completed' } as ExecutionRun
  expect(executionDecisionLabel(run)).toContain('не требуется')
  expect(executionDecisionLabel({ ...run, task_type: 'irrigation_start' })).toContain('не сохранено')
})
