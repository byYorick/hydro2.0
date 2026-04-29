export type IrrigationSystemType =
  | 'drip_tape'
  | 'drip_emitter'
  | 'ebb_flow'
  | 'nft'
  | 'dwc'
  | 'aeroponics'

export type CorrectionProfile = 'safe' | 'balanced' | 'aggressive' | 'test'

export type IrrigationDecisionStrategy = 'task' | 'smart_soil_v1'

export interface IrrigationConfig {
  duration_sec: number
  interval_sec: number
  correction_during_irrigation: boolean
  correction_slack_sec: number
}

export interface IrrigationDecisionConfig {
  lookback_sec?: number
  min_samples?: number
  stale_after_sec?: number
  hysteresis_pct?: number
  spread_alert_threshold_pct?: number
}

export interface IrrigationDecision {
  strategy: IrrigationDecisionStrategy
  config?: IrrigationDecisionConfig | null
}

/** Задержки min-check и флаги fail-safe AE3/NodeConfig при старте зоны. */
export interface StartupFailSafeGuardsConfig {
  clean_fill_min_check_delay_ms: number
  solution_fill_clean_min_check_delay_ms: number
  solution_fill_solution_min_check_delay_ms: number
  recirculation_stop_on_solution_min: boolean
  irrigation_stop_on_solution_min: boolean
  estop_debounce_ms: number
}

export interface StartupConfig {
  clean_fill_timeout_sec: number
  solution_fill_timeout_sec: number
  prepare_recirculation_timeout_sec: number
  level_poll_interval_sec: number
  clean_fill_retry_cycles: number
  fail_safe_guards?: StartupFailSafeGuardsConfig
}

export interface ZoneAutomationPresetConfig {
  irrigation: IrrigationConfig
  irrigation_decision: IrrigationDecision
  startup: StartupConfig
  climate?: Record<string, unknown> | null
  lighting?: Record<string, unknown> | null
}

export interface ZoneAutomationPreset {
  id: number
  name: string
  slug: string
  description: string | null
  scope: 'system' | 'custom'
  is_locked: boolean
  tanks_count: 2 | 3
  irrigation_system_type: IrrigationSystemType
  correction_preset_id: number | null
  correction_profile: CorrectionProfile | null
  config: ZoneAutomationPresetConfig
  created_by: number | null
  updated_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface ZoneAutomationPresetCreatePayload {
  name: string
  description?: string | null
  tanks_count: 2 | 3
  irrigation_system_type: IrrigationSystemType
  correction_preset_id?: number | null
  correction_profile?: CorrectionProfile | null
  config: ZoneAutomationPresetConfig
}

export interface ZoneAutomationPresetUpdatePayload {
  name?: string
  description?: string | null
  tanks_count?: 2 | 3
  irrigation_system_type?: IrrigationSystemType
  correction_preset_id?: number | null
  correction_profile?: CorrectionProfile | null
  config?: Partial<ZoneAutomationPresetConfig>
}

export interface ZoneAutomationPresetFilters {
  tanks_count?: 2 | 3
  irrigation_system_type?: IrrigationSystemType
}
