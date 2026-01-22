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
  | 'GROWTH_CYCLE_CONFIG'
  | string

/**
 * Статус команды (новые значения из единого контракта)
 */
export type CommandStatus =
  | 'QUEUED'      // Команда поставлена в очередь
  | 'SENT'        // Команда отправлена в MQTT
  | 'ACK'         // Команда принята узлом
  | 'DONE'        // Команда успешно выполнена
  | 'NO_EFFECT'   // Команда выполнена без эффекта
  | 'ERROR'       // Команда завершилась с ошибкой
  | 'INVALID'     // Команда отклонена как некорректная
  | 'BUSY'        // Команда отклонена, узел занят
  | 'TIMEOUT'     // Команда не получила ответа в срок
  | 'SEND_FAILED' // Ошибка при отправке команды
  | 'UNKNOWN'     // Неизвестный статус
  

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
