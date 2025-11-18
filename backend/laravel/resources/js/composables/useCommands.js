/**
 * Composable для отправки команд зонам и узлам
 */
import { ref, computed } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi } from './useApi'

/**
 * Composable для работы с командами
 * @param {Function} showToast - Функция для показа Toast уведомлений
 * @returns {Object} Методы для работы с командами
 */
export function useCommands(showToast = null) {
  const { api } = useApi(showToast)
  const loading = ref(false)
  const error = ref(null)
  const pendingCommands = ref(new Map()) // Map<commandId, { status, zoneId, type }>

  /**
   * Отправить команду зоне
   * @param {number} zoneId - ID зоны
   * @param {string} type - Тип команды (FORCE_IRRIGATION, FORCE_PH_CONTROL, etc.)
   * @param {Object} params - Параметры команды
   * @returns {Promise<Object>} Результат команды
   */
  async function sendZoneCommand(zoneId, type, params = {}) {
    loading.value = true
    error.value = null

    try {
      const response = await api.post(`/api/zones/${zoneId}/commands`, {
        type,
        params
      })

      const commandId = response.data?.data?.id || response.data?.id
      
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

      return response.data?.data || response.data
    } catch (err) {
      error.value = err
      const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
      
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
   * @param {number} nodeId - ID узла
   * @param {string} type - Тип команды
   * @param {Object} params - Параметры команды
   * @returns {Promise<Object>} Результат команды
   */
  async function sendNodeCommand(nodeId, type, params = {}) {
    loading.value = true
    error.value = null

    try {
      const response = await api.post(`/api/nodes/${nodeId}/commands`, {
        type,
        params
      })

      const commandId = response.data?.data?.id || response.data?.id
      
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

      return response.data?.data || response.data
    } catch (err) {
      error.value = err
      const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
      
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
   * @param {number|string} commandId - ID команды
   * @returns {Promise<Object>} Статус команды
   */
  async function getCommandStatus(commandId) {
    try {
      const response = await api.get(`/api/commands/${commandId}/status`)
      const status = response.data?.data || response.data
      
      // Обновляем статус в pendingCommands
      if (pendingCommands.value.has(commandId)) {
        const command = pendingCommands.value.get(commandId)
        command.status = status.status || 'unknown'
        pendingCommands.value.set(commandId, command)
      }
      
      return status
    } catch (err) {
      error.value = err
      if (showToast) {
        showToast('Ошибка при получении статуса команды', 'error', 5000)
      }
      throw err
    }
  }

  /**
   * Обновить статус команды (вызывается из WebSocket)
   * @param {number|string} commandId - ID команды
   * @param {string} status - Новый статус (pending, executing, completed, failed)
   * @param {string} message - Сообщение (опционально)
   */
  function updateCommandStatus(commandId, status, message = null) {
    if (pendingCommands.value.has(commandId)) {
      const command = pendingCommands.value.get(commandId)
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
   * @returns {Array} Список ожидающих команд
   */
  function getPendingCommands() {
    return Array.from(pendingCommands.value.entries()).map(([id, command]) => ({
      id,
      ...command
    }))
  }

  /**
   * Очистить завершенные команды из списка ожидающих
   * @param {number} maxAge - Максимальный возраст команды в миллисекундах (по умолчанию 5 минут)
   */
  function clearCompletedCommands(maxAge = 5 * 60 * 1000) {
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
   * @param {number} zoneId - ID зоны
   * @param {Array<string>} only - Список props для обновления
   */
  function reloadZoneAfterCommand(zoneId, only = ['zone', 'cycles']) {
    router.reload({ only })
  }

  return {
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    pendingCommands: computed(() => getPendingCommands()),
    sendZoneCommand,
    sendNodeCommand,
    getCommandStatus,
    updateCommandStatus,
    clearCompletedCommands,
    reloadZoneAfterCommand,
  }
}

