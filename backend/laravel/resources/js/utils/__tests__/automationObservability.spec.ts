import { describe, expect, it } from 'vitest'
import {
  formatObservabilityDuration,
  normalizeActiveDoses,
  normalizeObservability,
  observabilityHealthLabel,
  resolveCorrectionDosingDiagnostics,
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

  it('drops non-finite task_id and event_id during normalization', () => {
    const result = normalizeObservability({
      overall_health: 'active',
      runtime: {
        zone_id: 1,
        task_id: 'not-a-number',
        task_status: 'running',
      },
      correction: {
        latest_skip: {
          event_id: 'bad',
          event_type: 'CORRECTION_SKIPPED_COOLDOWN',
          age_sec: 'x',
        },
      },
      hang_hints: [],
    })

    expect(result?.runtime?.task_id).toBeNull()
    expect(result?.correction?.latest_skip?.event_id).toBeNull()
    expect(result?.correction?.latest_skip?.age_sec).toBeNull()
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
      active_processes: { pump_in: true, circulation_pump: false, ph_correction: false, ec_correction: false, active_doses: [] },
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
      active_processes: { pump_in: true, circulation_pump: false, ph_correction: false, ec_correction: false, active_doses: [] },
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

  it('normalizes correction context from observability payload', () => {
    const result = normalizeObservability({
      overall_health: 'active',
      correction: {
        last_dose: {
          ec: { last_dose_at: '2026-07-09T10:00:00Z', last_dose_age_sec: 120, no_effect_count: 1 },
        },
        latest_skip: {
          event_type: 'CORRECTION_SKIPPED_WINDOW_NOT_READY',
          payload: { ph_reason: 'sensor_out_of_bounds', retry_after_sec: 30 },
        },
        readiness: {
          targets_in_tolerance: true,
          workflow_ready: false,
        },
      },
    })

    expect(result?.correction?.last_dose?.ec?.no_effect_count).toBe(1)
    expect(result?.correction?.latest_skip?.event_type).toBe('CORRECTION_SKIPPED_WINDOW_NOT_READY')
    expect(result?.correction?.readiness?.workflow_ready).toBe(false)
  })

  it('resolves correction dosing diagnostics from skip event and corr step', () => {
    const diagnostics = resolveCorrectionDosingDiagnostics(
      {
        zone_id: 1,
        state: 'IRRIGATING',
        state_label: 'Полив',
        workflow_phase: 'irrigating',
        control_mode: 'auto',
        state_details: { started_at: null, elapsed_sec: 10, progress_percent: 0, failed: false },
        system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
        current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: 6.0, ec: 1.5 },
        active_processes: { pump_in: false, circulation_pump: true, ph_correction: false, ec_correction: true, active_doses: [] },
        timeline: [],
        next_state: null,
        estimated_completion_sec: null,
      },
      {
        runtime: {
          task_is_active: true,
          correction_step: 'corr_check',
          workflow_phase: 'irrigating',
        },
        correction: {
          latest_skip: {
            event_type: 'EC_BATCH_PARTIAL_FAILURE',
            age_sec: 30,
            payload: { failed_component: 'magnesium', status: 'degraded' },
          },
        },
      },
    )

    expect(diagnostics?.visible).toBe(true)
    expect(diagnostics?.reason).toContain('частичный сбой')
    expect(diagnostics?.severity).toBe('danger')
    expect(diagnostics?.detail).toContain('magnesium')
  })

  it('prefers active dosing over stale soft skip', () => {
    const diagnostics = resolveCorrectionDosingDiagnostics(
      {
        zone_id: 1,
        state: 'IRRIGATING',
        state_label: 'Полив',
        workflow_phase: 'irrigating',
        control_mode: 'auto',
        state_details: { started_at: null, elapsed_sec: 10, progress_percent: 0, failed: false },
        system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
        current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: 6.0, ec: 1.5 },
        active_processes: {
          pump_in: false,
          circulation_pump: true,
          ph_correction: false,
          ec_correction: true,
          active_doses: [
            {
              kind: 'ec',
              channel: 'pump_b',
              component: 'calcium',
              node_uid: 'nd-ec',
              amount_ml: 2.5,
              duration_ms: 2500,
            },
          ],
        },
        timeline: [],
        next_state: null,
        estimated_completion_sec: null,
      },
      {
        runtime: {
          task_is_active: true,
          correction_step: 'corr_dose_ec',
          workflow_phase: 'irrigating',
        },
        correction: {
          active_doses: [
            {
              kind: 'ec',
              channel: 'pump_b',
              component: 'calcium',
              node_uid: 'nd-ec',
              amount_ml: 2.5,
              duration_ms: 2500,
            },
          ],
          latest_skip: {
            event_type: 'CORRECTION_SKIPPED_COOLDOWN',
            age_sec: 5,
            payload: { retry_after_sec: 60 },
          },
        },
      },
    )

    expect(diagnostics?.reason).toBe('Дозирование выполняется')
    expect(diagnostics?.isDosingActive).toBe(true)
    expect(diagnostics?.severity).toBe('info')
    expect(diagnostics?.detail).toBeNull()
    expect(diagnostics?.activeDoses).toHaveLength(1)
    expect(diagnostics?.activeDoses[0]?.channel).toBe('pump_b')
  })

  it('normalizes active_doses and drops invalid entries', () => {
    expect(normalizeActiveDoses([
      { kind: 'ph_down', channel: 'Pump_Acid', amount_ml: 1.2, duration_ms: 1200 },
      { kind: 'invalid', channel: 'pump_x' },
      { kind: 'ec', channel: '' },
      { kind: 'ec', channel: 'pump_a', component: 'NPK' },
    ])).toEqual([
      {
        kind: 'ph_down',
        channel: 'pump_acid',
        component: null,
        node_uid: null,
        amount_ml: 1.2,
        duration_ms: 1200,
      },
      {
        kind: 'ec',
        channel: 'pump_a',
        component: 'npk',
        node_uid: null,
        amount_ml: null,
        duration_ms: null,
      },
    ])
  })

  it('hides dosing card on idle even with stale skip/readiness', () => {
    const diagnostics = resolveCorrectionDosingDiagnostics(
      {
        zone_id: 1,
        state: 'IDLE',
        state_label: 'Ожидание',
        workflow_phase: 'idle',
        control_mode: 'auto',
        state_details: { started_at: null, elapsed_sec: 0, progress_percent: 0, failed: false },
        system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
        current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: null, ec: null },
        active_processes: { pump_in: false, circulation_pump: false, ph_correction: false, ec_correction: false, active_doses: [] },
        timeline: [],
        next_state: null,
        estimated_completion_sec: null,
      },
      {
        runtime: { task_is_active: false, workflow_phase: 'idle' },
        correction: {
          latest_skip: {
            event_type: 'CORRECTION_SKIPPED_COOLDOWN',
            age_sec: 10,
            payload: { retry_after_sec: 60 },
          },
          readiness: { targets_in_tolerance: true, workflow_ready: false },
        },
      },
    )

    expect(diagnostics).toBeNull()
  })

  it('shows manual control_mode block when correction is active', () => {
    const diagnostics = resolveCorrectionDosingDiagnostics(
      {
        zone_id: 1,
        state: 'IRRIGATING',
        state_label: 'Полив',
        workflow_phase: 'irrigating',
        control_mode: 'manual',
        state_details: { started_at: null, elapsed_sec: 10, progress_percent: 0, failed: false },
        system_config: { tanks_count: 2, system_type: 'drip', clean_tank_capacity_l: null, nutrient_tank_capacity_l: null },
        current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0, ph: 6.0, ec: 1.5 },
        active_processes: { pump_in: false, circulation_pump: true, ph_correction: false, ec_correction: true, active_doses: [] },
        timeline: [],
        next_state: null,
        estimated_completion_sec: null,
      },
      {
        runtime: {
          task_is_active: true,
          correction_step: 'corr_check',
          workflow_phase: 'irrigating',
        },
      },
    )

    expect(diagnostics?.reason).toContain('Ручной режим')
    expect(diagnostics?.severity).toBe('warning')
  })
})
