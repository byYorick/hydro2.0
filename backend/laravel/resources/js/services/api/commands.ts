/**
 * Commands domain API client.
 *
 * Эндпоинты:
 *   POST /api/zones/:zoneId/commands
 *   POST /api/nodes/:nodeId/commands
 *   GET  /api/commands/:commandId/status
 *
 * Backend возвращает результат в нескольких формах:
 *   1. { data: { id, type, ... } } — полный объект команды
 *   2. { data: { command_id: '<uuid>' } } — только cmd_id из PythonBridge
 *   3. { id, type, ... } — прямой объект команды
 *
 * Эта неоднородность — контрактная проблема backend'а, поэтому клиент
 * возвращает union-type `CommandSendResult`, а нормализация остаётся
 * в composable useCommands.
 */
import type { Command, CommandParams, CommandStatus, CommandType } from '@/types'
import { apiGet, apiPost } from './_client'

export type CommandSendResult =
  | ({ id: number | string; type: CommandType } & Partial<Command>)
  | { command_id: number | string }

export interface SendCommandPayload {
  type: CommandType
  params: CommandParams
  channel?: string
}

export const commandsApi = {
  sendZoneCommand(zoneId: number, payload: SendCommandPayload): Promise<CommandSendResult> {
    return apiPost<CommandSendResult>(`/zones/${zoneId}/commands`, payload)
  },

  sendNodeCommand(nodeId: number, payload: SendCommandPayload): Promise<CommandSendResult> {
    return apiPost<CommandSendResult>(`/nodes/${nodeId}/commands`, payload)
  },

  getStatus(commandId: number | string): Promise<{ status: CommandStatus }> {
    return apiGet<{ status: CommandStatus }>(`/commands/${commandId}/status`)
  },
}
