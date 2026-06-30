import { describe, expect, it } from 'vitest'
import {
  formatObservabilityDuration,
  normalizeObservability,
  observabilityHealthLabel,
  resolveObservability,
  stageDiagnosticLabel,
} from '@/utils/automationObservability'

describe('automationObservability', () => {
  it('normalizes hang hints and runtime block', () => {
    const result = normalizeObservability({
      overall_health: 'warning',
      runtime: {
        zone_id: 3,
        task_status: 'waiting_command',
        waiting_command: true,
        stage_elapsed_sec: 240,
        current_stage: 'clean_fill_check',
      },
      hang_hints: [
        {
          code: 'waiting_command_stuck',
          severity: 'warning',
          message: 'Ждём команду',
          recommendation: 'Проверьте MQTT',
        },
      ],
    })

    expect(result?.overall_health).toBe('warning')
    expect(result?.runtime?.waiting_command).toBe(true)
    expect(result?.hang_hints).toHaveLength(1)
    expect(result?.hang_hints?.[0]?.code).toBe('waiting_command_stuck')
  })

  it('preserves failed_stage in runtime normalization', () => {
    const result = normalizeObservability({
      overall_health: 'idle',
      runtime: {
        zone_id: 1,
        task_id: 3,
        task_status: 'failed',
        task_is_active: false,
        failed_stage: 'prepare_recirculation_start',
        stage_elapsed_sec: 27,
      },
      hang_hints: [],
    })

    expect(result?.runtime?.failed_stage).toBe('prepare_recirculation_start')
  })

  it('formats duration and stage labels', () => {
    expect(formatObservabilityDuration(125)).toBe('02:05')
    expect(stageDiagnosticLabel('solution_fill_check')).toBe('Наполнение раствором')
    expect(observabilityHealthLabel('critical')).toBe('Критично')
  })

  it('builds client fallback when observability missing', () => {
    const result = resolveObservability({
      zone_id: 9,
      state: 'TANK_FILLING',
      state_label: 'Наполнение',
      state_details: { started_at: null, elapsed_sec: 30, progress_percent: 10, failed: false },
      workflow_phase: 'tank_filling',
      current_stage: 'clean_fill_check',
      system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
      current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: null, ec: null },
      active_processes: { pump_in: true, circulation_pump: false, ph_correction: false, ec_correction: false },
      timeline: [],
      next_state: null,
      estimated_completion_sec: null,
      state_meta: { is_stale: true, source: 'cache', served_at: '2026-06-23T12:00:00Z' },
    })

    expect(result?.runtime?.source).toBe('client_fallback')
    expect(result?.hang_hints?.some((hint) => hint.code === 'state_snapshot_stale')).toBe(true)
  })

  it('appends stale snapshot hint when observability exists but cache is stale', () => {
    const result = resolveObservability({
      zone_id: 9,
      state: 'TANK_FILLING',
      state_label: 'Наполнение',
      state_details: { started_at: null, elapsed_sec: 30, progress_percent: 10, failed: false },
      workflow_phase: 'tank_filling',
      current_stage: 'clean_fill_check',
      system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
      current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: null, ec: null },
      active_processes: { pump_in: true, circulation_pump: false, ph_correction: false, ec_correction: false },
      timeline: [],
      next_state: null,
      estimated_completion_sec: null,
      state_meta: { is_stale: true, source: 'cache', served_at: '2026-06-23T12:00:00Z' },
      observability: {
        overall_health: 'active',
        runtime: { task_is_active: true, task_status: 'running' },
        hang_hints: [],
      },
    })

    expect(result?.hang_hints?.some((hint) => hint.code === 'state_snapshot_stale')).toBe(true)
    expect(result?.overall_health).toBe('warning')
  })
})
