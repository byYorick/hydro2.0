import type { Zone } from './Zone'

/**
 * Тип устройства
 */
export type DeviceType = 'sensor' | 'actuator' | 'controller' | 'ph' | 'ec' | 'pump' | 'climate'

/**
 * Статус устройства
 */
export type DeviceStatus = 'online' | 'offline' | 'degraded' | 'unknown'

export interface PumpCalibrationConfig {
  ml_per_sec?: number
  k_ms_per_ml_l?: number
  duration_sec?: number
  actual_ml?: number
  component?: 'npk' | 'calcium' | 'magnesium' | 'micro' | 'ph_up' | 'ph_down' | string | null
  test_volume_l?: number
  ec_before_ms?: number
  ec_after_ms?: number
  delta_ec_ms?: number
  temperature_c?: number
  calibrated_at?: string | null
}

/**
 * Канал устройства
 */
export interface DeviceChannel {
  id?: number
  node_id?: number
  channel: string
  type: 'SENSOR' | 'ACTUATOR' | string
  metric: string | number | null
  unit: string | null
  config?: Record<string, unknown>
  pump_calibration?: PumpCalibrationConfig | null
  actuator_type?: string | null
  description?: string | null
}

/**
 * Конфигурация устройства
 */
export interface DeviceConfig {
  sample_rate?: number
  [key: string]: unknown
}

/**
 * Модель устройства
 */
export type NodeLifecycleState = 
  | 'MANUFACTURED'
  | 'UNPROVISIONED'
  | 'PROVISIONED_WIFI'
  | 'REGISTERED_BACKEND'
  | 'ASSIGNED_TO_ZONE'
  | 'ACTIVE'
  | 'DEGRADED'
  | 'MAINTENANCE'
  | 'DECOMMISSIONED'

export interface Device {
  id: number
  uid: string
  name?: string
  type: DeviceType
  status: DeviceStatus
  lifecycle_state?: NodeLifecycleState
  fw_version?: string
  config?: DeviceConfig
  zone?: Zone
  zone_id?: number
  channels?: DeviceChannel[]
  last_seen_at?: string
  created_at?: string
  updated_at?: string
}
