export interface SystemSettingsField {
  path: string
  label: string
  description: string
  type: 'number' | 'integer' | 'string' | 'boolean' | 'json'
  min?: number
  max?: number
  step?: number
}

export interface SystemSettingsSection {
  key: string
  label: string
  description: string
  fields: SystemSettingsField[]
}

export interface SettingsNamespacePayload<TConfig extends Record<string, unknown> = Record<string, unknown>> {
  namespace: string
  config: TConfig
  meta: {
    defaults: TConfig
    field_catalog: SystemSettingsSection[]
  }
}

export interface PumpCalibrationSettings {
  ml_per_sec_min: number
  ml_per_sec_max: number
  min_dose_ms: number
  calibration_duration_min_sec: number
  calibration_duration_max_sec: number
  quality_score_basic: number
  quality_score_with_k: number
  quality_score_legacy: number
  age_warning_days: number
  age_critical_days: number
  default_run_duration_sec: number
}

export interface SensorCalibrationSettings {
  ph_point_1_value: number
  ph_point_2_value: number
  ec_point_1_tds: number
  ec_point_2_tds: number
  reminder_days: number
  critical_days: number
  command_timeout_sec: number
  ph_reference_min: number
  ph_reference_max: number
  ec_tds_reference_max: number
}

export interface AutomationDefaultsSettings {
  climate_enabled: boolean
  climate_day_temp_c: number
  climate_night_temp_c: number
  climate_day_humidity_pct: number
  climate_night_humidity_pct: number
  climate_interval_min: number
  climate_day_start_hhmm: string
  climate_night_start_hhmm: string
  climate_vent_min_pct: number
  climate_vent_max_pct: number
  climate_use_external_telemetry: boolean
  climate_outside_temp_min_c: number
  climate_outside_temp_max_c: number
  climate_outside_humidity_max_pct: number
  climate_manual_override_enabled: boolean
  climate_manual_override_minutes: number
  water_system_type: 'drip' | 'substrate_trays' | 'nft'
  water_tanks_count: 2 | 3
  water_clean_tank_fill_l: number
  water_nutrient_tank_target_l: number
  water_irrigation_batch_l: number
  water_interval_min: number
  water_duration_sec: number
  water_fill_temperature_c: number
  water_fill_window_start_hhmm: string
  water_fill_window_end_hhmm: string
  water_target_ph: number
  water_target_ec: number
  water_ph_pct: number
  water_ec_pct: number
  water_valve_switching_enabled: boolean
  water_correction_during_irrigation: boolean
  water_drain_control_enabled: boolean
  water_drain_target_pct: number
  water_diagnostics_enabled: boolean
  water_diagnostics_interval_min: number
  water_cycle_start_workflow_enabled: boolean
  water_diagnostics_workflow: 'startup' | 'cycle_start' | 'diagnostics'
  water_clean_tank_full_threshold: number
  water_refill_duration_sec: number
  water_refill_timeout_sec: number
  water_startup_clean_fill_timeout_sec: number
  water_startup_solution_fill_timeout_sec: number
  water_startup_prepare_recirculation_timeout_sec: number
  water_startup_clean_fill_retry_cycles: number
  water_startup_level_poll_interval_sec: number
  water_startup_level_switch_on_threshold: number
  water_startup_clean_max_sensor_label: string
  water_startup_solution_max_sensor_label: string
  water_irrigation_recovery_max_continue_attempts: number
  water_irrigation_recovery_timeout_sec: number
  water_irrigation_recovery_target_tolerance_ec_pct: number
  water_irrigation_recovery_target_tolerance_ph_pct: number
  water_irrigation_recovery_degraded_tolerance_ec_pct: number
  water_irrigation_recovery_degraded_tolerance_ph_pct: number
  water_prepare_tolerance_ec_pct: number
  water_prepare_tolerance_ph_pct: number
  water_correction_max_ec_attempts: number
  water_correction_max_ph_attempts: number
  water_correction_prepare_recirculation_max_attempts: number
  water_correction_prepare_recirculation_max_correction_attempts: number
  water_correction_stabilization_sec: number
  water_two_tank_clean_fill_start_steps: number
  water_two_tank_clean_fill_stop_steps: number
  water_two_tank_solution_fill_start_steps: number
  water_two_tank_solution_fill_stop_steps: number
  water_two_tank_prepare_recirculation_start_steps: number
  water_two_tank_prepare_recirculation_stop_steps: number
  water_two_tank_irrigation_recovery_start_steps: number
  water_two_tank_irrigation_recovery_stop_steps: number
  water_refill_required_node_types_csv: string
  water_refill_preferred_channel: string
  water_solution_change_enabled: boolean
  water_solution_change_interval_min: number
  water_solution_change_duration_sec: number
  water_manual_irrigation_sec: number
  lighting_enabled: boolean
  lighting_lux_day: number
  lighting_lux_night: number
  lighting_hours_on: number
  lighting_interval_min: number
  lighting_schedule_start_hhmm: string
  lighting_schedule_end_hhmm: string
  lighting_manual_intensity_pct: number
  lighting_manual_duration_hours: number
}

export interface AutomationCommandTemplateStep {
  channel: string
  cmd: 'set_relay'
  params: {
    state: boolean
  }
}

export interface AutomationCommandTemplatesSettings {
  clean_fill_start: AutomationCommandTemplateStep[]
  clean_fill_stop: AutomationCommandTemplateStep[]
  solution_fill_start: AutomationCommandTemplateStep[]
  solution_fill_stop: AutomationCommandTemplateStep[]
  prepare_recirculation_start: AutomationCommandTemplateStep[]
  prepare_recirculation_stop: AutomationCommandTemplateStep[]
  irrigation_recovery_start: AutomationCommandTemplateStep[]
  irrigation_recovery_stop: AutomationCommandTemplateStep[]
}
