import { ref, type Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { normalizeStatus } from '@/composables/useCommands'
import { logger } from '@/utils/logger'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { api } from '@/services/api'
import type { Device } from '@/types'
import type { ToastHandler } from '@/services/api'

interface UseDeviceCommandActionsOptions {
  device: Ref<Device>
  showToast: ToastHandler
  upsertDevice: (device: Device) => void
}

const COMMAND_ERROR_MESSAGES: Record<string, string> = {
  relay_not_initialized: 'Релейный драйвер не инициализирован',
  relay_invalid_channel: 'Неверное имя канала реле',
  relay_channel_not_found: 'Канал реле не найден',
  relay_mutex_timeout: 'Таймаут выполнения команды реле',
  relay_gpio_error: 'Ошибка управления GPIO реле',
  relay_error: 'Ошибка управления реле',
  invalid_params: 'Неверные параметры команды',
  set_time_failed: 'Не удалось установить время на ноде',
}

function formatCommandError(status: string, errorMessage?: string, errorCode?: string): string {
  const localized = resolveHumanErrorMessage({
    code: errorCode,
    message: errorMessage,
  })
  if (localized) {
    return localized
  }

  if (errorCode && COMMAND_ERROR_MESSAGES[errorCode]) {
    return COMMAND_ERROR_MESSAGES[errorCode]
  }

  if (errorMessage) {
    return errorMessage
  }

  if (errorCode) {
    return `Код ошибки: ${errorCode}`
  }

  return status
}

function isStorageLevelSwitchChannel(nodeType: string, channelName: string, channelType: string): boolean {
  const normalizedNodeType = (nodeType || '').toLowerCase()
  const normalizedChannelName = (channelName || '').toLowerCase()
  const normalizedChannelType = (channelType || '').toLowerCase()

  return normalizedNodeType === 'irrig'
    && normalizedChannelType === 'sensor'
    && normalizedChannelName.startsWith('level_')
}

function isIrrigationServiceStateChannel(nodeType: string, channelName: string): boolean {
  return (nodeType || '').toLowerCase() === 'irrig'
    && (channelName || '').toLowerCase() === 'storage_state'
}

function isIrrigationActuatorChannel(nodeType: string, channelName: string, channelType: string): boolean {
  const normalizedNodeType = (nodeType || '').toLowerCase()
  const normalizedChannelName = (channelName || '').toLowerCase()
  const normalizedChannelType = (channelType || '').toLowerCase()

  return normalizedNodeType === 'irrig' && (
    normalizedChannelType === 'actuator'
    || normalizedChannelName.startsWith('pump_')
    || normalizedChannelName.startsWith('valve_')
  )
}

export function useDeviceCommandActions({
  device,
  showToast,
  upsertDevice,
}: UseDeviceCommandActionsOptions): {
  testingChannels: Ref<Set<string>>
  detaching: Ref<boolean>
  detachModalOpen: Ref<boolean>
  onRestart: () => Promise<void>
  detachNode: () => Promise<void>
  confirmDetachNode: () => Promise<void>
  onTestPump: (channelName: string, channelType: string) => Promise<void>
} {
  const testingChannels = ref<Set<string>>(new Set())
  const detaching = ref(false)
  const detachModalOpen = ref(false)

  async function checkCommandStatus(
    cmdId: string | number,
    maxAttempts = 30,
    onStatusChange?: (status: string) => void
  ): Promise<{
    success: boolean
    status: string
    error?: string
    errorCode?: string
    errorMessage?: string
    humanErrorMessage?: string
  }> {
    let lastStatus: string | null = null
    for (let i = 0; i < maxAttempts; i++) {
      try {
        const payload = await api.commands.getStatus(cmdId) as {
          status?: string
          error_message?: string | null
          error_code?: string | null
          human_error_message?: string | null
        }

        if (payload && typeof payload.status === 'string') {
          const normalizedStatus = normalizeStatus(payload.status)
          if (normalizedStatus !== lastStatus) {
            lastStatus = normalizedStatus
            onStatusChange?.(normalizedStatus)
          }
          if (['DONE', 'NO_EFFECT'].includes(normalizedStatus)) {
            return { success: true, status: normalizedStatus }
          }
          if (['ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'].includes(normalizedStatus)) {
            const errorMessage = payload.error_message || undefined
            const errorCode = payload.error_code || undefined
            const humanErrorMessage = payload.human_error_message || undefined
            return {
              success: false,
              status: normalizedStatus,
              error: errorMessage || errorCode || undefined,
              errorCode,
              errorMessage,
              humanErrorMessage,
            }
          }
          if (['QUEUED', 'SENT', 'ACK'].includes(normalizedStatus)) {
            await new Promise(resolve => setTimeout(resolve, 500))
            continue
          }
        }
      } catch (err) {
        logger.error('[Devices/Show] Failed to check command status:', err)
        const errorStatus = (err as { response?: { status?: number } })?.response?.status
        if (errorStatus === 404 && i < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, 500))
          continue
        }
        const errorMessage = err instanceof Error ? err.message : 'Unknown error'
        return { success: false, status: 'ERROR', error: errorMessage }
      }
    }

    return { success: false, status: 'TIMEOUT' }
  }

  function getChannelLabel(channelName: string, channelType: string): string {
    const name = (channelName || '').toLowerCase()
    const nodeType = (device.value.type || '').toLowerCase()
    const type = (channelType || '').toLowerCase()
    const isSensor = type === 'sensor'

    if (nodeType === 'ph') {
      if (isSensor && name.includes('ph_sensor')) return 'Тест pH сенсора'
      if (isSensor && (name.includes('solution_temp') || name.includes('temp'))) return 'Тест температуры раствора'
      if (name.includes('acid') || name.includes('up')) return 'PH UP тест'
      if (name.includes('base') || name.includes('down')) return 'PH DOWN тест'
    }

    if (nodeType === 'ec') {
      if (name.includes('nutrient_a') || name.includes('pump_a')) return 'Тест насоса A'
      if (name.includes('nutrient_b') || name.includes('pump_b')) return 'Тест насоса B'
      if (name.includes('nutrient_c') || name.includes('pump_c')) return 'Тест насоса C'
      if (name.includes('nutrient')) return 'Тест насоса питательного раствора'
    }

    if (nodeType === 'irrig') {
      if (name.includes('main') || name.includes('primary')) return 'Тест главного насоса'
      if (name.includes('backup') || name.includes('reserve')) return 'Тест резервного насоса'
      if (name.includes('transfer') || name.includes('перекач')) return 'Тест перекачивающего насоса'
      if (name.includes('valve') || channelType === 'valve') return 'Тест клапана'
    }

    if (isSensor) return `Тест сенсора ${channelName || 'канал'}`
    return channelName || 'Канал'
  }

  async function onRestart(): Promise<void> {
    try {
      const response = await api.commands.sendNodeCommand(device.value.id, {
        type: 'restart',
        params: {},
      }) as { command_id?: string | number; id?: string | number }

      const cmdId = response?.command_id ?? response?.id
      if (cmdId) {
        showToast('Команда перезапуска отправлена', 'success', TOAST_TIMEOUT.NORMAL)

        let executionNotified = false
        const result = await checkCommandStatus(cmdId, 20, (status) => {
          if (status === 'ACK' && !executionNotified) {
            executionNotified = true
            showToast('Перезапуск ноды...', 'info', TOAST_TIMEOUT.NORMAL)
          }
        })

        if (result.success) {
          showToast('Нода перезапущена', 'success', TOAST_TIMEOUT.LONG)
        } else {
          const detail = result.humanErrorMessage || formatCommandError(result.status, result.errorMessage, result.errorCode)
          showToast(`Ошибка перезапуска: ${detail}`, 'error', TOAST_TIMEOUT.LONG)
        }
        return
      }

      showToast('Не удалось отправить команду перезапуска', 'error', TOAST_TIMEOUT.LONG)
    } catch (err) {
      logger.error('[Devices/Show] Failed to restart device:', err)
    }
  }

  async function detachNode(): Promise<void> {
    if (!device.value.zone_id) {
      showToast('Нода уже отвязана от зоны', 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    detachModalOpen.value = true
  }

  async function confirmDetachNode(): Promise<void> {
    if (!device.value.zone_id) {
      detachModalOpen.value = false
      return
    }

    detaching.value = true
    try {
      const updatedDevice = await api.nodes.detach(device.value.id)

      showToast(`Нода "${device.value.uid || device.value.name}" успешно отвязана от зоны`, 'success', TOAST_TIMEOUT.NORMAL)

      const nextDevice = updatedDevice || {
        ...device.value,
        zone_id: undefined,
        zone: undefined,
      }

      if (nextDevice?.id) {
        upsertDevice(nextDevice as Device)
      }
    } catch (err) {
      logger.error('[Devices/Show] Failed to detach node:', err)
    } finally {
      detaching.value = false
      detachModalOpen.value = false
    }
  }

  async function onTestPump(channelName: string, channelType: string): Promise<void> {
    if (testingChannels.value.has(channelName)) {
      return
    }

    testingChannels.value.add(channelName)
    const channelLabel = getChannelLabel(channelName, channelType)
    showToast(`Команда отправлена: ${channelLabel}`, 'info', TOAST_TIMEOUT.SHORT)

    try {
      let commandType = 'run_pump'
      let params: Record<string, unknown> = { duration_ms: 3000 }

      const nodeTypeLower = (device.value.type || '').toLowerCase()
      const channelNameLower = (channelName || '').toLowerCase()
      const channelTypeLower = (channelType || '').toLowerCase()

      const isRelayNode = nodeTypeLower.includes('relay')
      const isSensor = channelTypeLower === 'sensor'
      const isValve = channelTypeLower === 'valve' || channelNameLower.includes('valve')
      const isStorageLevelSwitch = isStorageLevelSwitchChannel(nodeTypeLower, channelNameLower, channelTypeLower)
      const isIrrigationServiceState = isIrrigationServiceStateChannel(nodeTypeLower, channelNameLower)
      const isIrrigationActuator = isIrrigationActuatorChannel(nodeTypeLower, channelNameLower, channelTypeLower)

      if (isStorageLevelSwitch) {
        commandType = 'state'
        channelName = 'storage_state'
        params = {}
      } else if (isIrrigationServiceState) {
        commandType = 'state'
        params = {}
      } else if (isSensor) {
        commandType = 'test_sensor'
        params = {}
      } else if (isIrrigationActuator) {
        commandType = 'set_relay'
        params = { state: true, duration_ms: 3000 }
      } else if (isRelayNode) {
        commandType = 'set_relay'
        params = { state: 1, duration_ms: 3000 }
      } else if (isValve) {
        commandType = 'set_relay'
        params = { state: true, duration_ms: 3000 }
      }

      const response = await api.commands.sendNodeCommand(device.value.id, {
        type: commandType as never,
        channel: channelName,
        params: params as never,
      }) as { command_id?: string | number; id?: string | number }

      const cmdId = response?.command_id ?? response?.id
      if (cmdId) {
        let executionNotified = false
        const result = await checkCommandStatus(cmdId, 30, (status) => {
          if (status === 'ACK' && !executionNotified) {
            executionNotified = true
            showToast(`Выполнение: ${channelLabel}...`, 'info', TOAST_TIMEOUT.NORMAL)
          }
        })

        if (result.success) {
          showToast(`Выполнено: ${channelLabel}`, 'success', TOAST_TIMEOUT.LONG)
        } else {
          const detail = result.humanErrorMessage || formatCommandError(result.status, result.errorMessage, result.errorCode)
          showToast(`Ошибка теста ${channelLabel}: ${detail}`, 'error', TOAST_TIMEOUT.LONG)
        }
      } else {
        showToast(`Не удалось отправить команду для ${channelLabel}`, 'error', TOAST_TIMEOUT.LONG)
      }
    } catch (err) {
      const apiMessage = (err as { response?: { data?: { message?: string; error?: string } } })?.response?.data
      const detail = resolveHumanErrorMessage({
        message: apiMessage?.message || apiMessage?.error || null,
      })
      if (detail) {
        showToast(`Ошибка теста ${channelLabel}: ${detail}`, 'error', TOAST_TIMEOUT.LONG)
      }
      logger.error(`[Devices/Show] Failed to test ${channelName}:`, err)
    } finally {
      testingChannels.value.delete(channelName)
    }
  }

  return {
    testingChannels,
    detaching,
    detachModalOpen,
    onRestart,
    detachNode,
    confirmDetachNode,
    onTestPump,
  }
}
