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
  | 'solution_fill_stop'
  | 'prepare_recirculation_start'
  | 'prepare_recirculation_stop'
  | 'irrigation_recovery_start'
  | 'irrigation_recovery_stop'

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
    elapsed_sec: number
    progress_percent: number
    failed?: boolean
    error_code?: string | null
    error_message?: string | null
  }
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
