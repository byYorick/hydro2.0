import { describe, expect, it } from 'vitest'
import {
  automationHasTerminalFailure,
  automationIndicatesActiveFailure,
  automationIndicatesHistoricalFailure,
  timelineIndicatesTerminalFailure,
} from '@/utils/automationFailureState'
import type { AutomationState } from '@/types/Automation'

function baseState(overrides: Partial<AutomationState> = {}): AutomationState {
  return {
    zone_id: 1,
    state: 'READY',
    state_label: 'Готово',
    state_details: {
      started_at: null,
      elapsed_sec: 0,
      progress_percent: 100,
      failed: false,
    },
    system_config: {
      tanks_count: 2,
      system_type: 'drip',
      clean_tank_capacity_l: null,
      nutrient_tank_capacity_l: null,
    },
    current_levels: {
      clean_tank_level_percent: 50,
      nutrient_tank_level_percent: 50,
      ph: 6,
      ec: 1.5,
    },
    active_processes: {
      pump_in: false,
      circulation_pump: false,
      ph_correction: false,
      ec_correction: false,
    active_doses: [],
    },
    timeline: [],
    next_state: null,
    estimated_completion_sec: null,
    ...overrides,
  }
}

describe('automationFailureState', () => {
  it('определяет исторический сбой через last_terminal_failure', () => {
    const state = baseState({
      last_terminal_failure: {
        error_code: 'command_timeout',
        human_error_message: 'Таймаут',
      },
    })

    expect(automationIndicatesHistoricalFailure(state)).toBe(true)
    expect(automationHasTerminalFailure(state)).toBe(true)
    // После ack алерта workflow/баннер процесса смотрят только active failure.
    expect(automationIndicatesActiveFailure(state)).toBe(false)
  })

  it('определяет terminal failure по timeline', () => {
    const state = baseState({
      timeline: [{ event: 'TASK_FAILED', at: '2026-06-29T10:00:00Z', label: 'fail' }],
    })

    expect(timelineIndicatesTerminalFailure(state)).toBe(true)
    expect(automationHasTerminalFailure(state)).toBe(true)
  })
})
