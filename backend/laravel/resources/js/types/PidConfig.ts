/**
 * Коэффициенты PID для одной зоны.
 */
export interface PidZoneCoeffs {
  kp: number
  ki: number
  kd: number
}

/**
 * PID конфигурация зоны (pH или EC).
 * Хранится в authority zone PID document payload.
 */
export interface PidConfig {
  dead_zone: number
  close_zone: number
  far_zone: number
  zone_coeffs: {
    close: PidZoneCoeffs
    far: PidZoneCoeffs
  }
  max_integral: number
  autotune_meta?: PidAutotuneMeta
}

/**
 * Метаданные relay autotune после завершения.
 */
export interface PidAutotuneMeta {
  source: 'relay_autotune'
  ku: number
  tu_sec: number
  oscillation_amplitude: number
  cycles_detected: number
  tuned_at: string
}

/**
 * PID конфиг с метаданными из API.
 */
export interface PidConfigWithMeta {
  type: 'ph' | 'ec'
  config: PidConfig
  is_default?: boolean
  updated_at?: string
  updated_by?: number
}

export type PidConfigRecord = Record<'ph' | 'ec', PidConfigWithMeta | null>

/**
 * Лог PID вывода (из zone_events PID_OUTPUT / PID_CONFIG_UPDATED).
 */
export interface PidLog {
  id: number
  type: 'ph' | 'ec' | 'config_updated'
  zone_state?: 'dead' | 'close' | 'far'
  output?: number
  error?: number
  integral_term?: number
  dt_seconds?: number
  current?: number
  target?: number
  safety_skip_reason?: string
  pid_type?: 'ph' | 'ec'
  old_config?: PidConfig
  new_config?: PidConfig
  updated_by?: number
  created_at: string
}

/**
 * Калибровка одного дозирующего насоса.
 */
export interface PumpCalibration {
  node_channel_id: number
  role: string
  component: string
  channel_label: string
  node_uid: string
  channel: string
  ml_per_sec: number | null
  k_ms_per_ml_l: number | null
  source: string | null
  valid_from: string | null
  is_active: boolean
  calibration_age_days?: number | null
}

/**
 * Статус relay autotune для зоны.
 */
export interface RelayAutotuneStatus {
  zone_id: number
  pid_type: 'ph' | 'ec'
  status: 'idle' | 'running' | 'complete' | 'timeout'
  started_at?: string
  completed_at?: string
  result?: PidAutotuneMeta
  progress?: {
    cycles_detected: number
    min_cycles: number
    elapsed_sec: number
    max_duration_sec: number
  }
}
