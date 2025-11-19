import type { Zone } from './Zone'

/**
 * Тип устройства
 */
export type DeviceType = 'sensor' | 'actuator' | 'controller' | 'ph' | 'ec' | 'pump' | 'climate'

/**
 * Статус устройства
 */
export type DeviceStatus = 'online' | 'offline' | 'degraded' | 'unknown'

/**
 * Канал устройства
 */
export interface DeviceChannel {
  channel: string
  type: 'SENSOR' | 'ACTUATOR'
  metric: number | null
  unit: string | null
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
export interface Device {
  id: number
  uid: string
  name?: string
  type: DeviceType
  status: DeviceStatus
  fw_version?: string
  config?: DeviceConfig
  zone?: Zone
  zone_id?: number
  channels?: DeviceChannel[]
  last_seen_at?: string
  created_at?: string
  updated_at?: string
}
