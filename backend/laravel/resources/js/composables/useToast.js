/**
 * Composable для централизованного управления Toast уведомлениями
 */
import { ref } from 'vue'

// Глобальное хранилище для Toast уведомлений
const toasts = ref([])
let toastIdCounter = 0

/**
 * Очистить все toasts (для тестирования)
 */
export function clearAllToasts() {
  toasts.value = []
  toastIdCounter = 0
}

/**
 * Composable для работы с Toast уведомлениями
 * @returns {Object} Методы для управления Toast
 */
export function useToast() {
  /**
   * Показать Toast уведомление
   * @param {string} message - Сообщение
   * @param {string} variant - Тип (success, error, warning, info)
   * @param {number} duration - Длительность в миллисекундах
   * @returns {number} ID уведомления
   */
  function showToast(message, variant = 'info', duration = 3000) {
    const id = ++toastIdCounter
    const toast = {
      id,
      message,
      variant,
      duration
    }
    
    toasts.value.push(toast)
    
    // Автоматическое удаление через duration
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration)
    }
    
    return id
  }

  /**
   * Удалить Toast уведомление
   * @param {number} id - ID уведомления
   */
  function removeToast(id) {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Показать успешное уведомление
   * @param {string} message - Сообщение
   * @param {number} duration - Длительность
   */
  function success(message, duration = 3000) {
    return showToast(message, 'success', duration)
  }

  /**
   * Показать уведомление об ошибке
   * @param {string} message - Сообщение
   * @param {number} duration - Длительность
   */
  function error(message, duration = 5000) {
    return showToast(message, 'error', duration)
  }

  /**
   * Показать предупреждение
   * @param {string} message - Сообщение
   * @param {number} duration - Длительность
   */
  function warning(message, duration = 4000) {
    return showToast(message, 'warning', duration)
  }

  /**
   * Показать информационное уведомление
   * @param {string} message - Сообщение
   * @param {number} duration - Длительность
   */
  function info(message, duration = 3000) {
    return showToast(message, 'info', duration)
  }

  /**
   * Очистить все уведомления
   */
  function clearAll() {
    toasts.value = []
  }

  return {
    toasts,
    showToast,
    removeToast,
    success,
    error,
    warning,
    info,
    clearAll
  }
}

