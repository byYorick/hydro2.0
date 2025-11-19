/**
 * Composable для централизованного управления Toast уведомлениями
 */
import { ref, type Ref } from 'vue'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  message: string
  variant: ToastVariant
  duration: number
}

// Глобальное хранилище для Toast уведомлений
const toasts: Ref<Toast[]> = ref([])
let toastIdCounter = 0

/**
 * Очистить все toasts (для тестирования)
 */
export function clearAllToasts(): void {
  toasts.value = []
  toastIdCounter = 0
}

/**
 * Composable для работы с Toast уведомлениями
 */
export function useToast() {
  /**
   * Показать Toast уведомление
   */
  function showToast(
    message: string,
    variant: ToastVariant = 'info',
    duration: number = 3000
  ): number {
    const id = ++toastIdCounter
    const toast: Toast = {
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
   */
  function removeToast(id: number): void {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Показать успешное уведомление
   */
  function success(message: string, duration: number = 3000): number {
    return showToast(message, 'success', duration)
  }

  /**
   * Показать уведомление об ошибке
   */
  function error(message: string, duration: number = 5000): number {
    return showToast(message, 'error', duration)
  }

  /**
   * Показать предупреждение
   */
  function warning(message: string, duration: number = 4000): number {
    return showToast(message, 'warning', duration)
  }

  /**
   * Показать информационное уведомление
   */
  function info(message: string, duration: number = 3000): number {
    return showToast(message, 'info', duration)
  }

  /**
   * Очистить все уведомления
   */
  function clearAll(): void {
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

