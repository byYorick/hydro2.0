export type AutomationStateType =
  | 'IDLE'
  | 'TANK_FILLING'
  | 'TANK_RECIRC'
  | 'READY'
  | 'IRRIGATING'
  | 'IRRIG_RECIRC'

export interface AutomationTimelineEvent {
  event: string
  timestamp: string
  label?: string
  active?: boolean
}

export interface AutomationState {
  zone_id: number
  state: AutomationStateType
  state_label: string
  state_details: {
    started_at: string | null
    elapsed_sec: number
    progress_percent: number
  }
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
}

export interface HoveredElement {
  title: string
  data: Record<string, string>
  x: number
  y: number
}
