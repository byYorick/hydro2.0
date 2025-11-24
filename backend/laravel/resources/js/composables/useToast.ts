/**
 * Composable для централизованного управления Toast уведомлениями
 */
import { ref, type Ref } from 'vue'

// Группировка похожих уведомлений
const groupedToasts = new Map<string, number[]>()

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface ToastAction {
  label: string
  variant?: 'primary' | 'secondary'
  handler: () => void
}

export interface Toast {
  id: number
  message: string
  variant: ToastVariant
  duration: number
  title?: string
  actions?: ToastAction[]
  grouped?: boolean
  showProgress?: boolean
  progress?: number
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
    duration: number = 3000,
    options?: {
      title?: string
      actions?: ToastAction[]
      groupKey?: string
      showProgress?: boolean
    }
  ): number {
    const id = ++toastIdCounter
    
    // Проверяем группировку
    let grouped = false
    if (options?.groupKey) {
      const existingGroup = groupedToasts.get(options.groupKey)
      if (existingGroup && existingGroup.length > 0) {
        grouped = true
        // Обновляем существующее уведомление вместо создания нового
        const existingId = existingGroup[existingGroup.length - 1]
        const existingToast = toasts.value.find(t => t.id === existingId)
        if (existingToast) {
          existingToast.message = `${existingToast.message}\n${message}`
          return existingId
        }
      } else {
        groupedToasts.set(options.groupKey, [id])
      }
    }
    
    const toast: Toast = {
      id,
      message,
      variant,
      duration,
      title: options?.title,
      actions: options?.actions,
      grouped,
      showProgress: options?.showProgress ?? true,
      progress: 100
    }
    
    toasts.value.push(toast)
    
    // Обновление прогресс-бара
    if (duration > 0 && toast.showProgress) {
      const startTime = Date.now()
      const interval = setInterval(() => {
        const elapsed = Date.now() - startTime
        const remaining = Math.max(0, 100 - (elapsed / duration) * 100)
        const toastIndex = toasts.value.findIndex(t => t.id === id)
        if (toastIndex > -1) {
          toasts.value[toastIndex].progress = remaining
        }
        if (remaining <= 0) {
          clearInterval(interval)
        }
      }, 50)
    }
    
    // Автоматическое удаление через duration
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
        if (options?.groupKey) {
          const group = groupedToasts.get(options.groupKey)
          if (group) {
            const index = group.indexOf(id)
            if (index > -1) {
              group.splice(index, 1)
            }
            if (group.length === 0) {
              groupedToasts.delete(options.groupKey)
            }
          }
        }
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

