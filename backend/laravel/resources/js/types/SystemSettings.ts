export interface SystemSettingsField {
  path: string
  label: string
  description: string
  type: 'number' | 'integer' | 'string' | 'boolean'
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
