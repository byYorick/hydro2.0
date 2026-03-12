import type { Greenhouse } from './Greenhouse'
import type { RecipeInstance } from './Recipe'
import type { Device } from './Device'
import type { Cycle } from './Cycle'
import type { ZoneTargets } from './ZoneTargets'
import type { ZoneTelemetry } from './Telemetry'

/**
 * Статус зоны
 */
export type ZoneStatus = 'RUNNING' | 'PAUSED' | 'ALARM' | 'WARNING' | 'IDLE'

/**
 * Модель зоны
 */
export interface Zone {
  id: number
  uid: string
  name: string
  description?: string
  status: ZoneStatus
  greenhouse_id: number
  greenhouse?: Greenhouse
  recipe_instance?: RecipeInstance
  targets: ZoneTargets
  telemetry?: ZoneTelemetry
  devices?: Device[]
  cycles?: Cycle[]
  created_at: string
  updated_at: string
}
