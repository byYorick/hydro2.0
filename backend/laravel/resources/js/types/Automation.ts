export type AutomationStateType =
  | 'IDLE'
  | 'TANK_FILLING'
  | 'TANK_RECIRC'
  | 'READY'
  | 'IRRIGATING'
  | 'IRRIG_RECIRC'

export type AutomationControlMode = 'auto' | 'semi' | 'manual'

export type AutomationManualStep =
  | 'clean_fill_start'
  | 'clean_fill_stop'
  | 'solution_fill_start'
  | 'force_solution_fill_start'
  | 'solution_fill_stop'
  | 'prepare_recirculation_stop'
  | 'irrigation_stop'
  | 'irrigation_recovery_stop'
  | 'solution_drain_confirm'
  | 'solution_refill_confirm'
  | 'solution_change_abort'

export interface AutomationTimelineEvent {
  event: string
  timestamp: string
  label?: string
  active?: boolean
}

export interface IrrNodeState {
  clean_level_max: boolean | null
  clean_level_min: boolean | null
  solution_level_max: boolean | null
  solution_level_min: boolean | null
  valve_clean_fill: boolean | null
  valve_clean_supply: boolean | null
  valve_solution_fill: boolean | null
  valve_solution_supply: boolean | null
  valve_irrigation: boolean | null
  pump_main: boolean | null
  updated_at?: string | null
}

export interface AutomationState {
  zone_id: number
  state: AutomationStateType
  state_label: string
  state_details: {
    started_at: string | null
    stage_entered_at?: string | null
    elapsed_sec: number
    progress_percent: number
    progress_basis?: string | null
    stage_deadline_remaining_sec?: number | null
    failed?: boolean
    error_code?: string | null
    error_message?: string | null
    human_error_message?: string | null
    failed_task_id?: number | null
  }
  last_terminal_failure?: {
    task_id?: number | null
    failed_at?: string | null
    error_code?: string | null
    error_message?: string | null
    human_error_message?: string | null
  } | null
  workflow_phase?: string | null
  current_stage?: string | null
  current_stage_label?: string | null
  system_config: {
    tanks_count: 2 | 3
    system_type: 'drip' | 'substrate_trays' | 'nft'
    clean_tank_capacity_l: number | null
    nutrient_tank_capacity_l: number | null
  }
  current_levels: {
    clean_tank_level_percent: number
    nutrient_tank_level_percent: number
    buffer_tank_level_percent?: number | null
    ph: number | null
    ec: number | null
  }
  active_processes: {
    pump_in: boolean
    circulation_pump: boolean
    ph_correction: boolean
    ec_correction: boolean
  }
  timeline: AutomationTimelineEvent[]
  next_state: AutomationStateType | null
  estimated_completion_sec: number | null
  irr_node_state?: IrrNodeState | null
  control_mode?: AutomationControlMode
  control_mode_available?: AutomationControlMode[]
  allowed_manual_steps?: AutomationManualStep[]
  state_meta?: {
    source?: string
    is_stale?: boolean
    served_at?: string
  } | null
  decision?: {
    outcome?: string | null
    reason_code?: string | null
    strategy?: string | null
    config?: Record<string, unknown> | null
    bundle_revision?: string | null
    degraded?: boolean | null
  } | null
  observability?: AutomationObservability | null
}

export type AutomationObservabilityHealth = 'idle' | 'active' | 'warning' | 'critical'

export type AutomationHangHintSeverity = 'warning' | 'critical' | 'info'

export interface AutomationHangHint {
  code: string
  severity: AutomationHangHintSeverity
  message: string
  recommendation?: string | null
  details?: Record<string, unknown>
}

export interface AutomationObservabilityRuntime {
  zone_id: number
  task_id?: number | null
  task_status?: string | null
  task_is_active?: boolean
  current_stage?: string | null
  workflow_phase?: string | null
  stage_entered_at?: string | null
  stage_elapsed_sec?: number
  stage_deadline_at?: string | null
  stage_deadline_remaining_sec?: number | null
  waiting_command?: boolean
  waiting_elapsed_sec?: number
  task_updated_age_sec?: number | null
  correction_step?: string | null
  pending_manual_step?: string | null
  topology?: string | null
  workflow_snapshot_updated_at?: string | null
  workflow_snapshot_age_sec?: number | null
  source?: string | null
  /** Этап на момент terminal failure (после workflow rollback в idle). */
  failed_stage?: string | null
}

export interface AutomationObservabilityNode {
  uid?: string | null
  type?: string | null
  status?: string | null
  last_seen_age_sec?: number | null
  required?: boolean
  healthy?: boolean
}

export interface AutomationObservabilityScheduler {
  pending_count?: number
  active_count?: number
  latest_intent?: {
    id?: number
    status?: string
    intent_type?: string
    not_before?: string | null
    created_at?: string | null
    updated_at?: string | null
    age_sec?: number | null
  } | null
}

export interface AutomationObservabilityCorrectionDose {
  last_dose_at?: string | null
  last_dose_age_sec?: number | null
  no_effect_count?: number
}

export interface AutomationObservabilityCorrectionSkip {
  event_id?: number | null
  event_type?: string | null
  occurred_at?: string | null
  age_sec?: number | null
  payload?: Record<string, unknown>
}

export interface AutomationObservabilityCorrectionReadiness {
  event_id?: number | null
  event_type?: string | null
  occurred_at?: string | null
  targets_in_tolerance?: boolean | null
  workflow_ready?: boolean | null
}

export interface AutomationObservabilityCorrection {
  last_dose?: Record<string, AutomationObservabilityCorrectionDose>
  latest_skip?: AutomationObservabilityCorrectionSkip | null
  readiness?: AutomationObservabilityCorrectionReadiness | null
}

export interface AutomationObservability {
  runtime?: AutomationObservabilityRuntime
  nodes?: {
    nodes?: AutomationObservabilityNode[]
    offline_required?: string[]
    persistent_offline?: boolean
  }
  scheduler?: AutomationObservabilityScheduler
  hang_hints?: AutomationHangHint[]
  overall_health?: AutomationObservabilityHealth
  correction?: AutomationObservabilityCorrection
}

export type CorrectionDosingBlockSeverity = 'neutral' | 'info' | 'warning' | 'danger'

export interface CorrectionDosingDiagnostics {
  visible: boolean
  corrStep: string | null
  corrStepLabel: string | null
  reason: string | null
  detail: string | null
  lastDoseSummary: string | null
  cooldownLabel: string | null
  targetsInTolerance: boolean | null
  workflowReady: boolean | null
  severity: CorrectionDosingBlockSeverity
  isDosingActive: boolean
}

export interface HoveredElement {
  title: string
  data: Record<string, string>
  x: number
  y: number
}

/**
 * Типы стадий workflow автоматизации (синхронизированы с backend state machine)
 */
export type WorkflowStageCode = 'tank_filling' | 'tank_recirc' | 'ready' | 'irrigating' | 'irrig_recirc'
export type WorkflowStageStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface WorkflowStageView {
  code: WorkflowStageCode
  label: string
  status: WorkflowStageStatus
}
