import type { Zone } from './Zone'
import type { Device } from './Device'

/**
 * Тип команды
 */
export type CommandType =
  | 'FORCE_IRRIGATION'
  | 'FORCE_PH_CONTROL'
  | 'FORCE_EC_CONTROL'
  | 'FORCE_CLIMATE'
  | 'FORCE_LIGHTING'
  | 'FORCE_PH_CONTROL'
  | 'FORCE_EC_CONTROL'
  | string

/**
 * Статус команды
 */
export type CommandStatus = 'pending' | 'executing' | 'completed' | 'failed' | 'unknown'

/**
 * Параметры команды
 */
export interface CommandParams {
  [key: string]: unknown
}

/**
 * Модель команды
 */
export interface Command {
  id: number
  type: CommandType
  status: CommandStatus
  zone_id?: number
  zone?: Zone
  node_id?: number
  node?: Device
  params?: CommandParams
  message?: string | null
  created_at: string
  updated_at?: string
  completed_at?: string
}

/**
 * Команда в ожидании (для отслеживания статуса)
 */
export interface PendingCommand {
  id: number | string
  status: CommandStatus
  zoneId?: number
  nodeId?: number
  type: CommandType
  timestamp: number
  message?: string
}
