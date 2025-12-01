/**
 * PID конфигурация
 */
export interface PidConfig {
  target: number
  dead_zone: number
  close_zone: number
  far_zone: number
  zone_coeffs: {
    close: { kp: number; ki: number; kd: number }
    far: { kp: number; ki: number; kd: number }
  }
  max_output: number
  min_interval_ms: number
  enable_autotune: boolean
  adaptation_rate: number
}

/**
 * PID конфиг с метаданными
 */
export interface PidConfigWithMeta {
  type: 'ph' | 'ec'
  config: PidConfig
  is_default?: boolean
  updated_at?: string
  updated_by?: number
}

/**
 * Лог PID вывода
 */
export interface PidLog {
  id: number
  type: 'ph' | 'ec' | 'config_updated'
  zone_state?: 'dead' | 'close' | 'far'
  output?: number
  error?: number
  dt_seconds?: number
  current?: number
  target?: number
  safety_skip_reason?: string
  pid_type?: 'ph' | 'ec' // для config_updated
  old_config?: PidConfig
  new_config?: PidConfig
  updated_by?: number
  created_at: string
}

