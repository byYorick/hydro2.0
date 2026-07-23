import { describe, expect, it } from 'vitest'
import type { AutomationState } from '@/types/Automation'
import { resolveAutomationFailureDiagnostics } from '@/utils/automationFailureDiagnostics'

function baseState(overrides: Partial<AutomationState> = {}): AutomationState {
  return {
    zone_id: 1,
    state: 'IDLE',
    state_label: 'Ожидание',
    state_details: {
      started_at: null,
      elapsed_sec: 0,
      progress_percent: 0,
      failed: false,
    },
    system_config: {
      tanks_count: 2,
      system_type: 'drip',
      clean_tank_capacity_l: null,
      nutrient_tank_capacity_l: null,
    },
    current_levels: {
      clean_tank_level_percent: 0,
      nutrient_tank_level_percent: 0,
      ph: null,
      ec: null,
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

describe('resolveAutomationFailureDiagnostics', () => {
  it('builds active failure context from state_details', () => {
    const result = resolveAutomationFailureDiagnostics(baseState({
      state_details: {
        started_at: null,
        elapsed_sec: 0,
        progress_percent: 0,
        failed: true,
        error_code: 'command_timeout',
        human_error_message: 'Не дождались подтверждения команды.',
        error_message: 'TIMEOUT',
        failed_task_id: 12,
      },
      observability: {
        runtime: {
          zone_id: 1,
          task_id: 12,
          task_status: 'failed',
          task_is_active: false,
          failed_stage: 'irrigation_check',
        },
      },
    }))

    expect(result?.isActiveFailure).toBe(true)
    expect(result?.summary).toContain('подтверждения')
    expect(result?.errorCode).toBe('command_timeout')
    expect(result?.failedStageLabel).toBe('Полив')
    expect(result?.taskId).toBe(12)
    expect(result?.technicalMessage).toBe('TIMEOUT')
  })

  it('uses last_terminal_failure when active failure was cleared after alert ack', () => {
    const result = resolveAutomationFailureDiagnostics(baseState({
      workflow_phase: 'idle',
      last_terminal_failure: {
        task_id: 3,
        failed_at: '2026-06-30T07:49:53+00:00',
        error_code: 'startup_recovery_unconfirmed_command',
        error_message: 'У задачи 3 отсутствует подтверждённая внешняя команда во время startup recovery',
        human_error_message: null,
      },
      observability: {
        runtime: {
          zone_id: 1,
          task_id: 3,
          task_status: 'failed',
          task_is_active: false,
          failed_stage: 'prepare_recirculation_start',
          workflow_phase: 'idle',
          stage_elapsed_sec: 27,
        },
      },
    }))

    expect(result?.isHistoricalFailure).toBe(true)
    expect(result?.errorCode).toBe('startup_recovery_unconfirmed_command')
    expect(result?.summary).toContain('startup recovery')
    expect(result?.failedStageLabel).toBe('Запуск рециркуляции')
    expect(result?.taskId).toBe(3)
    expect(result?.failedAt).toBe('2026-06-30T07:49:53+00:00')
  })
})
