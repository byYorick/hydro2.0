import type { AutomationState, AutomationStateType, IrrNodeState, IrrigationDecisionEvidence } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import { hasExplicitControlMode, normalizeAutomationControlMode, normalizeAutomationControlModes, normalizeAutomationManualSteps, resolveAllowedManualSteps } from '@/composables/zoneAutomationUtils'
import { normalizeActiveDoses, normalizeObservability } from '@/utils/automationObservability'
import { normalizeDayBalance, readOptionalSolutionTemp, readUnknownRecord } from '@/utils/cropDayView'

export function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'object' || (typeof value === 'string' && value.trim() === '')) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}
function optionalPercent(value: unknown): number | null {
  const n = optionalNumber(value)
  return n === null ? null : Math.max(0, Math.min(100, n))
}
export function clampPercent(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, parsed))
}

function toOptionalBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (value === 1) return true
    if (value === 0) return false
    return null
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === '1' || normalized === 'true') return true
    if (normalized === '0' || normalized === 'false') return false
  }
  return null
}

function normalizeIrrigationDecision(value: unknown): IrrigationDecisionEvidence | null {
  const raw = readUnknownRecord(value)
  if (!raw) return null
  const text = (key: string) => typeof raw[key] === 'string' ? raw[key] as string : null
  const taskId = raw.task_id == null ? null : Number(raw.task_id)
  return {
    task_id: taskId !== null && Number.isSafeInteger(taskId) && taskId > 0 ? taskId : null,
    task_status: text('task_status'), current_stage: text('current_stage'),
    created_at: text('created_at'), evaluated_at: text('evaluated_at'),
    outcome: text('outcome'), reason_code: text('reason_code'), strategy: text('strategy'),
    config: readUnknownRecord(raw.config), details: readUnknownRecord(raw.details),
    bundle_revision: text('bundle_revision'), degraded: toOptionalBoolean(raw.degraded),
    factors: readUnknownRecord(raw.factors),
  }
}

function normalizeIrrNodeState(raw: unknown): IrrNodeState | null {
  if (!raw || typeof raw !== 'object') return null
  const state = raw as Record<string, unknown>

  return {
    clean_level_max: toOptionalBoolean(state.clean_level_max),
    clean_level_min: toOptionalBoolean(state.clean_level_min),
    solution_level_max: toOptionalBoolean(state.solution_level_max),
    solution_level_min: toOptionalBoolean(state.solution_level_min),
    valve_clean_fill: toOptionalBoolean(state.valve_clean_fill),
    valve_clean_supply: toOptionalBoolean(state.valve_clean_supply),
    valve_solution_fill: toOptionalBoolean(state.valve_solution_fill),
    valve_solution_supply: toOptionalBoolean(state.valve_solution_supply),
    valve_irrigation: toOptionalBoolean(state.valve_irrigation),
    pump_main: toOptionalBoolean(state.pump_main),
    updated_at: typeof state.updated_at === 'string' ? state.updated_at : null,
  }
}

export function normalizeAutomationPanelState(raw: unknown, props: { zoneId: number | null; fallbackTanksCount?: number; fallbackSystemType?: IrrigationSystem }): AutomationState {
    const source = (raw && typeof raw === 'object' ? raw : {}) as Partial<AutomationState>
    const sourceAny = source as Record<string, unknown>
    const state = String(source.state ?? '') as AutomationStateType
    if (!['IDLE', 'TANK_FILLING', 'TANK_RECIRC', 'READY', 'IRRIGATING', 'IRRIG_RECIRC'].includes(state)) throw new Error('invalid_automation_state')
    const tanksRaw = Number(source.system_config?.tanks_count ?? props.fallbackTanksCount ?? 2)
    const tanksCount: 2 | 3 = tanksRaw === 3 ? 3 : 2

    const irrNodeStateRaw =
      sourceAny.irr_node_state
      ?? sourceAny.irrState
      ?? sourceAny.irrigation_node_state
      ?? (sourceAny.process_state && typeof sourceAny.process_state === 'object'
        ? (sourceAny.process_state as Record<string, unknown>).irr_node_state
        : undefined)
    const irrNodeState = normalizeIrrNodeState(irrNodeStateRaw)
    const compatibility = readUnknownRecord(sourceAny.compatibility)
    const lacksReadings = compatibility?.source === 'ae3_control_mode_fallback'


    return {
      zone_id: Number(source.zone_id ?? props.zoneId ?? 0),
      state,
      state_label: String(source.state_label || ''),
      state_details: {
        started_at: source.state_details?.started_at ?? null,
        stage_entered_at: (source.state_details as Record<string, unknown> | undefined)?.stage_entered_at as string | null ?? null,
        elapsed_sec: Number(source.state_details?.elapsed_sec ?? 0),
        progress_percent: clampPercent(source.state_details?.progress_percent ?? 0),
        progress_basis: (source.state_details as Record<string, unknown> | undefined)?.progress_basis as string | null ?? null,
        stage_deadline_remaining_sec: (() => {
          const raw = (source.state_details as Record<string, unknown> | undefined)?.stage_deadline_remaining_sec
          return raw == null ? null : Number(raw)
        })(),
        failed: Boolean(source.state_details?.failed ?? false),
        error_code: (source.state_details as Record<string, unknown> | undefined)?.error_code as string | null ?? null,
        error_message: (source.state_details as Record<string, unknown> | undefined)?.error_message as string | null ?? null,
        human_error_message: (source.state_details as Record<string, unknown> | undefined)?.human_error_message as string | null ?? null,
        failed_task_id: (() => {
          const raw = (source.state_details as Record<string, unknown> | undefined)?.failed_task_id
          if (raw == null) return null
          const parsed = Number(raw)
          return Number.isFinite(parsed) && parsed > 0 ? parsed : null
        })(),
      },
      last_terminal_failure: (() => {
        const raw = sourceAny.last_terminal_failure
        if (!raw || typeof raw !== 'object') return null
        const record = raw as Record<string, unknown>
        const taskIdRaw = record.task_id
        const taskId = taskIdRaw == null ? null : Number(taskIdRaw)
        return {
          task_id: Number.isFinite(taskId) && taskId > 0 ? taskId : null,
          failed_at: typeof record.failed_at === 'string' ? record.failed_at : null,
          error_code: typeof record.error_code === 'string' ? record.error_code : null,
          error_message: typeof record.error_message === 'string' ? record.error_message : null,
          human_error_message: typeof record.human_error_message === 'string' ? record.human_error_message : null,
        }
      })(),
      workflow_phase: (sourceAny.workflow_phase as string | null | undefined) ?? null,
      current_stage: (sourceAny.current_stage as string | null | undefined) ?? null,
      current_stage_label: (sourceAny.current_stage_label as string | null | undefined) ?? null,
      system_config: {
        tanks_count: tanksCount,
        system_type: (source.system_config?.system_type as IrrigationSystem) || props.fallbackSystemType || 'drip',
        clean_tank_capacity_l: source.system_config?.clean_tank_capacity_l ?? null,
        nutrient_tank_capacity_l: source.system_config?.nutrient_tank_capacity_l ?? null,
      },
      current_levels: {
        clean_tank_level_percent: lacksReadings ? null : optionalPercent(source.current_levels?.clean_tank_level_percent),
        nutrient_tank_level_percent: lacksReadings ? null : optionalPercent(source.current_levels?.nutrient_tank_level_percent),
        buffer_tank_level_percent: optionalPercent(source.current_levels?.buffer_tank_level_percent),
        ph: optionalNumber(source.current_levels?.ph),
        ec: optionalNumber(source.current_levels?.ec),
        solution_temp_c: readOptionalSolutionTemp(source.current_levels),
      },
      active_processes: {
        pump_in: toOptionalBoolean(source.active_processes?.pump_in) === true,
        circulation_pump: toOptionalBoolean(source.active_processes?.circulation_pump) === true,
        ph_correction: toOptionalBoolean(source.active_processes?.ph_correction) === true,
        ec_correction: toOptionalBoolean(source.active_processes?.ec_correction) === true,
        active_doses: normalizeActiveDoses(source.active_processes?.active_doses),
      },
      timeline: Array.isArray(source.timeline) ? source.timeline : [],
      next_state: source.next_state ?? null,
      estimated_completion_sec: source.estimated_completion_sec ?? null,
      irr_node_state: irrNodeState,
      ...(hasExplicitControlMode(sourceAny.control_mode)
        ? {
            control_mode: normalizeAutomationControlMode(sourceAny.control_mode),
            control_mode_available: normalizeAutomationControlModes(sourceAny.control_mode_available),
            allowed_manual_steps: resolveAllowedManualSteps(
              normalizeAutomationControlMode(sourceAny.control_mode),
              (sourceAny.current_stage as string | null | undefined) ?? null,
              normalizeAutomationManualSteps(sourceAny.allowed_manual_steps),
            ),
          }
        : {}),
      compatibility: compatibility && typeof compatibility.source === 'string' ? { source: compatibility.source } : null,
      state_meta: sourceAny.state_meta && typeof sourceAny.state_meta === 'object'
        ? {
            source: String((sourceAny.state_meta as Record<string, unknown>).source ?? ''),
            is_stale: toOptionalBoolean((sourceAny.state_meta as Record<string, unknown>).is_stale) ?? false,
            observed_at: typeof (sourceAny.state_meta as Record<string, unknown>).observed_at === 'string' ? (sourceAny.state_meta as Record<string, unknown>).observed_at as string : null,
            served_at: String((sourceAny.state_meta as Record<string, unknown>).served_at ?? ''),
          }
        : null,
      decision: normalizeIrrigationDecision(sourceAny.decision),
      irrigation_decision: normalizeIrrigationDecision(sourceAny.irrigation_decision),
      day_balance: normalizeDayBalance(sourceAny.day_balance),
      decision_factors: readUnknownRecord(sourceAny.decision_factors),
      observability: normalizeObservability(sourceAny.observability),
    }
  }
