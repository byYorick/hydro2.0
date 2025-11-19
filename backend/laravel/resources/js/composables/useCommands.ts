/**
 * Composable для отправки команд зонам и узлам
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi, type ToastHandler } from './useApi'
import type { Command, CommandType, CommandStatus, CommandParams, PendingCommand } from '@/types'

interface PendingCommandInternal {
  status: CommandStatus
  zoneId?: number
  nodeId?: number
  type: CommandType
  timestamp: number
  message?: string
}

/**
 * Composable для работы с командами
 */
export function useCommands(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<Error | null> = ref(null)
  const pendingCommands: Ref<Map<number | string, PendingCommandInternal>> = ref(new Map())

  /**
   * Отправить команду зоне
   */
  async function sendZoneCommand(
    zoneId: number,
    type: CommandType,
    params: CommandParams = {}
  ): Promise<Command> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ data?: Command } | Command>(
        `/api/zones/${zoneId}/commands`,
        {
          type,
          params
        }
      )

      const command = (response.data as { data?: Command })?.data || (response.data as Command)
      const commandId = command.id
      
      // Сохраняем информацию о команде для отслеживания статуса
      if (commandId) {
        pendingCommands.value.set(commandId, {
          status: 'pending',
          zoneId,
          type,
          timestamp: Date.now()
        })
      }

      if (showToast) {
        showToast(`Команда "${type}" отправлена успешно`, 'success', 3000)
      }

      return command
    } catch (err) {
      error.value = err as Error
      const errorMsg = (err as { response?: { data?: { message?: string } }; message?: string })
        ?.response?.data?.message || 
        (err as { message?: string })?.message || 
        'Неизвестная ошибка'
      
      if (showToast) {
        showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
      }
      
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Отправить команду узлу
   */
  async function sendNodeCommand(
    nodeId: number,
    type: CommandType,
    params: CommandParams = {}
  ): Promise<Command> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{ data?: Command } | Command>(
        `/api/nodes/${nodeId}/commands`,
        {
          type,
          params
        }
      )

      const command = (response.data as { data?: Command })?.data || (response.data as Command)
      const commandId = command.id
      
      if (commandId) {
        pendingCommands.value.set(commandId, {
          status: 'pending',
          nodeId,
          type,
          timestamp: Date.now()
        })
      }

      if (showToast) {
        showToast(`Команда "${type}" отправлена успешно`, 'success', 3000)
      }

      return command
    } catch (err) {
      error.value = err as Error
      const errorMsg = (err as { response?: { data?: { message?: string } }; message?: string })
        ?.response?.data?.message || 
        (err as { message?: string })?.message || 
        'Неизвестная ошибка'
      
      if (showToast) {
        showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
      }
      
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Получить статус команды
   */
  async function getCommandStatus(commandId: number | string): Promise<{ status: CommandStatus }> {
    try {
      const response = await api.get<{ data?: { status: CommandStatus } } | { status: CommandStatus }>(
        `/api/commands/${commandId}/status`
      )
      const status = (response.data as { data?: { status: CommandStatus } })?.data || 
                    (response.data as { status: CommandStatus })
      
      // Обновляем статус в pendingCommands
      if (pendingCommands.value.has(commandId)) {
        const command = pendingCommands.value.get(commandId)!
        command.status = status.status || 'unknown'
        pendingCommands.value.set(commandId, command)
      }
      
      return status
    } catch (err) {
      error.value = err as Error
      if (showToast) {
        showToast('Ошибка при получении статуса команды', 'error', 5000)
      }
      throw err
    }
  }

  /**
   * Обновить статус команды (вызывается из WebSocket)
   */
  function updateCommandStatus(
    commandId: number | string,
    status: CommandStatus,
    message: string | null = null
  ): void {
    if (pendingCommands.value.has(commandId)) {
      const command = pendingCommands.value.get(commandId)!
      command.status = status
      if (message) {
        command.message = message
      }
      pendingCommands.value.set(commandId, command)
      
      // Показываем уведомление при завершении
      if (status === 'completed' && showToast) {
        showToast(`Команда "${command.type}" выполнена успешно`, 'success', 3000)
      } else if (status === 'failed' && showToast) {
        showToast(`Команда "${command.type}" завершилась с ошибкой: ${message || 'Неизвестная ошибка'}`, 'error', 5000)
      }
    }
  }

  /**
   * Получить список ожидающих команд
   */
  function getPendingCommands(): PendingCommand[] {
    return Array.from(pendingCommands.value.entries()).map(([id, command]) => ({
      id,
      status: command.status,
      zoneId: command.zoneId,
      nodeId: command.nodeId,
      type: command.type,
      timestamp: command.timestamp,
      message: command.message,
    }))
  }

  /**
   * Очистить завершенные команды из списка ожидающих
   */
  function clearCompletedCommands(maxAge: number = 5 * 60 * 1000): void {
    const now = Date.now()
    for (const [id, command] of pendingCommands.value.entries()) {
      if (
        (command.status === 'completed' || command.status === 'failed') &&
        (now - command.timestamp) > maxAge
      ) {
        pendingCommands.value.delete(id)
      }
    }
  }

  /**
   * Обновить зону после выполнения команды через Inertia partial reload
   */
  function reloadZoneAfterCommand(zoneId: number, only: string[] = ['zone', 'cycles']): void {
    router.reload({ only })
  }

  return {
    loading: computed(() => loading.value) as ComputedRef<boolean>,
    error: computed(() => error.value) as ComputedRef<Error | null>,
    pendingCommands: computed(() => getPendingCommands()) as ComputedRef<PendingCommand[]>,
    sendZoneCommand,
    sendNodeCommand,
    getCommandStatus,
    updateCommandStatus,
    clearCompletedCommands,
    reloadZoneAfterCommand,
  }
}

