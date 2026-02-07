/**
 * Composable для централизованного управления Toast уведомлениями
 */
import { ref, type Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

// Группировка похожих уведомлений
const groupedToasts = new Map<string, number[]>()
const recentToasts = new Map<string, { id: number; timestamp: number }>()
const TOAST_DEDUPE_WINDOW_MS = 5000

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
  groupedToasts.clear()
  recentToasts.clear()
}

function cleanupRecentToasts(now: number): void {
  for (const [key, entry] of recentToasts.entries()) {
    if (now - entry.timestamp > TOAST_DEDUPE_WINDOW_MS) {
      recentToasts.delete(key)
    }
  }
}

function getToastDedupeKey(message: string, variant: ToastVariant, title?: string): string {
  return `${variant}::${title ?? ''}::${message}`
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
    duration: number = TOAST_TIMEOUT.NORMAL,
    options?: {
      title?: string
      actions?: ToastAction[]
      groupKey?: string
      showProgress?: boolean
      allowDuplicates?: boolean
    }
  ): number {
    const now = Date.now()
    cleanupRecentToasts(now)

    if (!options?.allowDuplicates) {
      const dedupeKey = getToastDedupeKey(message, variant, options?.title)
      const recent = recentToasts.get(dedupeKey)
      if (recent && now - recent.timestamp < TOAST_DEDUPE_WINDOW_MS) {
        const existingToast = toasts.value.find((toast) => toast.id === recent.id)
        if (existingToast) {
          return existingToast.id
        }
      }
    }

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
    recentToasts.set(getToastDedupeKey(message, variant, options?.title), {
      id,
      timestamp: now,
    })
    
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
  function success(message: string, duration: number = TOAST_TIMEOUT.NORMAL): number {
    return showToast(message, 'success', duration)
  }

  /**
   * Показать уведомление об ошибке
   */
  function error(message: string, duration: number = TOAST_TIMEOUT.LONG): number {
    return showToast(message, 'error', duration)
  }

  /**
   * Показать предупреждение
   */
  function warning(message: string, duration: number = TOAST_TIMEOUT.NORMAL): number {
    return showToast(message, 'warning', duration)
  }

  /**
   * Показать информационное уведомление
   */
  function info(message: string, duration: number = TOAST_TIMEOUT.NORMAL): number {
    return showToast(message, 'info', duration)
  }

  /**
   * Очистить все уведомления
   */
  function clearAll(): void {
    toasts.value = []
    groupedToasts.clear()
    recentToasts.clear()
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
