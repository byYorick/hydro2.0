/**
 * Composable для отправки команд зонам и узлам
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi, type ToastHandler } from './useApi'
import { useErrorHandler } from './useErrorHandler'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Command, CommandType, CommandStatus, CommandParams, PendingCommand } from '@/types'

interface PendingCommandInternal {
  status: CommandStatus
  zoneId?: number
  nodeId?: number
  type: CommandType
  timestamp: number
  message?: string
}

export function normalizeStatus(status: CommandStatus | string): CommandStatus {
  const statusUpper = String(status).toUpperCase()

  if ([
    'QUEUED',
    'SENT',
    'ACK',
    'DONE',
    'NO_EFFECT',
    'ERROR',
    'INVALID',
    'BUSY',
    'TIMEOUT',
    'SEND_FAILED'
  ].includes(statusUpper)) {
    return statusUpper as CommandStatus
  }

  return 'UNKNOWN'
}

/**
 * Composable для работы с командами
 */
export function useCommands(showToast?: ToastHandler) {
  const { api } = useApi(showToast || null)
  const { handleError } = useErrorHandler(showToast)
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
      const response = await api.post<{ data?: Command } | Command | { data?: { command_id?: string } }>(
        `/api/zones/${zoneId}/commands`,
        {
          type,
          params
        }
      )

      const raw = response.data as any

      // Пытаемся извлечь идентификатор команды из разных форматов ответа:
      // 1) { data: { id, type, ... } } - полный объект команды
      // 2) { data: { command_id: '<uuid>' } } - только cmd_id из PythonBridge
      // 3) { id, type, ... } - прямой объект команды
      let command: Command | null = null
      let commandId: number | string | null = null
      let commandType: CommandType = type

      if (raw?.data?.id) {
        command = raw.data as Command
        commandId = command.id
        commandType = command.type
      } else if (raw?.id) {
        command = raw as Command
        commandId = command.id
        commandType = command.type
      } else if (raw?.data?.command_id) {
        commandId = raw.data.command_id as string
        commandType = type
      }

      // Сохраняем информацию о команде для отслеживания статуса
      if (commandId) {
        pendingCommands.value.set(commandId, {
          status: 'QUEUED',
          zoneId,
          type: commandType,
          timestamp: Date.now(),
        })
      }

      if (showToast) {
        showToast(`Команда "${commandType}" отправлена успешно`, 'success', TOAST_TIMEOUT.NORMAL)
      }

      // Если API не вернул полный объект команды, возвращаем минимальный объект с id и type
      if (command) {
        return command
      }

      return {
        id: (commandId ?? Date.now()) as number,
        type: commandType,
        status: 'QUEUED',
        created_at: new Date().toISOString(),
      } as Command
    } catch (err) {
      error.value = err as Error
      const errorMsg = (err as { response?: { data?: { message?: string } }; message?: string })
        ?.response?.data?.message || 
        (err as { message?: string })?.message || 
        'Неизвестная ошибка'
      
      if (showToast) {
        showToast(`Ошибка: ${errorMsg}`, 'error', TOAST_TIMEOUT.LONG)
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
      const response = await api.post<{ data?: Command } | Command | { data?: { command_id?: string } }>(
        `/api/nodes/${nodeId}/commands`,
        {
          type,
          params
        }
      )

      const raw = response.data as any

      let command: Command | null = null
      let commandId: number | string | null = null
      let commandType: CommandType = type

      if (raw?.data?.id) {
        command = raw.data as Command
        commandId = command.id
        commandType = command.type
      } else if (raw?.id) {
        command = raw as Command
        commandId = command.id
        commandType = command.type
      } else if (raw?.data?.command_id) {
        commandId = raw.data.command_id as string
        commandType = type
      }
      
      if (commandId) {
        pendingCommands.value.set(commandId, {
          status: 'QUEUED',
          nodeId,
          type: commandType,
          timestamp: Date.now(),
        })
      }

      if (showToast) {
        showToast(`Команда "${commandType}" отправлена успешно`, 'success', TOAST_TIMEOUT.NORMAL)
      }

      if (command) {
        return command
      }

      return {
        id: (commandId ?? Date.now()) as number,
        type: commandType,
        status: 'QUEUED',
        created_at: new Date().toISOString(),
      } as Command
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useCommands',
        action: 'sendNodeCommand',
        nodeId,
        commandType: type,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
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
        const command = pendingCommands.value.get(commandId)
        if (command) {
          command.status = normalizeStatus(status.status || 'UNKNOWN')
          pendingCommands.value.set(commandId, command)
        }
      }
      
      return {
        status: normalizeStatus(status.status || 'UNKNOWN'),
      }
    } catch (err) {
      const normalizedError = handleError(err, {
        component: 'useCommands',
        action: 'getCommandStatus',
        commandId,
      })
      error.value = normalizedError instanceof Error ? normalizedError : new Error('Unknown error')
      throw normalizedError
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
    const normalizedStatus = normalizeStatus(status)
    if (pendingCommands.value.has(commandId)) {
      const command = pendingCommands.value.get(commandId)
      if (!command) {
        return
      }
      command.status = normalizedStatus
      if (message) {
        command.message = message
      }
      pendingCommands.value.set(commandId, command)
      
      // Показываем уведомление при завершении
      if (['DONE', 'NO_EFFECT'].includes(normalizedStatus) && showToast) {
        showToast(`Команда "${command.type}" выполнена успешно`, 'success', TOAST_TIMEOUT.NORMAL)
      } else if (['ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'].includes(normalizedStatus) && showToast) {
        showToast(`Команда "${command.type}" завершилась с ошибкой: ${message || 'Неизвестная ошибка'}`, 'error', TOAST_TIMEOUT.LONG)
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
        (['DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'].includes(command.status)) &&
        (now - command.timestamp) > maxAge
      ) {
        pendingCommands.value.delete(id)
      }
    }
  }

  const reloadTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const RELOAD_DEBOUNCE_MS = 500

  /**
   * Обновить зону после выполнения команды через API и store (вместо reload)
   * Используется для сохранения состояния страницы и избежания лишних перерисовок
   */
  function reloadZoneAfterCommand(zoneId: number, only: string[] = ['zone', 'cycles'], preserveUrl: boolean = true): void {
    const key = `${zoneId}:${only.join(',')}`
    
    const existingTimer = reloadTimers.get(key)
    if (existingTimer) {
      clearTimeout(existingTimer)
    }
    
    reloadTimers.set(key, setTimeout(async () => {
      reloadTimers.delete(key)
      logger.debug('[useCommands] Updating zone after command via API', { zoneId, only })
      
      // Импортируем динамически для избежания циклических зависимостей
      try {
        const { useZones } = await import('./useZones')
        const { useZonesStore } = await import('@/stores/zones')
        const { fetchZone } = useZones(showToast)
        const zonesStore = useZonesStore()
        
        const updatedZone = await fetchZone(zoneId, true) // forceRefresh = true
        if (updatedZone?.id) {
          zonesStore.upsert(updatedZone)
          logger.debug('[useCommands] Zone updated in store after command', { zoneId })
        }
      } catch (error) {
        logger.error('[useCommands] Failed to update zone after command, falling back to reload', { zoneId, error })
        // Fallback к частичному reload при ошибке
        router.reload({ only, preserveUrl })
      }
    }, RELOAD_DEBOUNCE_MS))
  }

  // Обработчик события reconciliation для обновления статусов команд при переподключении
  function handleReconciliation(event: CustomEvent) {
    const { commands } = event.detail || {}
    
    if (!commands || !Array.isArray(commands)) {
      return
    }

    logger.debug('[useCommands] Processing reconciliation commands data', {
      count: commands.length,
    })

    // Обновляем статусы команд из snapshot
    for (const cmd of commands) {
      if (!cmd.cmd_id) continue
      
      const commandId = cmd.cmd_id
      const status = normalizeStatus(cmd.status || 'UNKNOWN')
      
      // Обновляем только если команда еще не завершена или статус изменился
      if (pendingCommands.value.has(commandId)) {
        const existing = pendingCommands.value.get(commandId)
        if (existing && existing.status !== status) {
          pendingCommands.value.set(commandId, {
            ...existing,
            status,
            message: cmd.error_message,
            timestamp: cmd.ack_at || cmd.sent_at || cmd.created_at || Date.now(),
          })
          logger.debug('[useCommands] Updated command status from reconciliation', {
            commandId,
            oldStatus: existing.status,
            newStatus: status,
          })
        }
      } else if (!['DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'].includes(status)) {
        // Добавляем активные команды, которых еще нет в pendingCommands
        pendingCommands.value.set(commandId, {
          status,
          zoneId: cmd.zone_id,
          nodeId: cmd.node_id,
          type: cmd.type || 'unknown',
          timestamp: cmd.ack_at || cmd.sent_at || cmd.created_at || Date.now(),
          message: cmd.error_message,
        })
        logger.debug('[useCommands] Added command from reconciliation', {
          commandId,
          status,
        })
      }
    }

    logger.info('[useCommands] Reconciliation completed', {
      commandsProcessed: commands.length,
      pendingCount: pendingCommands.value.size,
    })
  }

  // Подписываемся на событие reconciliation при монтировании
  onMounted(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('ws:reconciliation:commands', handleReconciliation as EventListener)
    }
  })

  onUnmounted(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('ws:reconciliation:commands', handleReconciliation as EventListener)
    }
  })

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
