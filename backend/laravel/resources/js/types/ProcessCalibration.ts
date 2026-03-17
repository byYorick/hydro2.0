export type ProcessCalibrationMode = 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation'

export interface ProcessCalibrationMetaObserve {
  telemetry_period_sec?: number | null
  window_min_samples?: number | null
  decision_window_sec?: number | null
  observe_poll_sec?: number | null
  min_effect_fraction?: number | null
  stability_max_slope?: number | null
  no_effect_consecutive_limit?: number | null
}

export interface ZoneProcessCalibrationMeta {
  updated_by?: number | null
  batch?: string | null
  observe?: ProcessCalibrationMetaObserve | null
  [key: string]: unknown
}

export interface ZoneProcessCalibration {
  id: number
  zone_id: number
  mode: ProcessCalibrationMode
  ec_gain_per_ml: number | null
  ph_up_gain_per_ml: number | null
  ph_down_gain_per_ml: number | null
  ph_per_ec_ml: number | null
  ec_per_ph_ml: number | null
  transport_delay_sec: number | null
  settle_sec: number | null
  confidence: number | null
  source: string | null
  valid_from: string | null
  valid_to: string | null
  is_active: boolean
  meta?: ZoneProcessCalibrationMeta | null
}

export interface ZoneProcessCalibrationForm {
  ec_gain_per_ml: string
  ph_up_gain_per_ml: string
  ph_down_gain_per_ml: string
  ph_per_ec_ml: string
  ec_per_ph_ml: string
  transport_delay_sec: string
  settle_sec: string
  confidence: string
}
