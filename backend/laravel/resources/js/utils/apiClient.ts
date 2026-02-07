/**
 * Единый модуль конфигурации HTTP клиента (axios)
 * Все настройки CSRF, baseURL, interceptors централизованы здесь
 */
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosRequestHeaders } from 'axios'
import { logger } from './logger'
import { ERROR_MESSAGES } from '@/constants/messages'
import type { ToastAction, ToastVariant } from '@/composables/useToast'

// Тип функции для показа Toast
export type ToastHandler = (
  message: string,
  variant?: ToastVariant,
  duration?: number,
  options?: {
    title?: string
    actions?: ToastAction[]
    groupKey?: string
    showProgress?: boolean
    allowDuplicates?: boolean
  }
) => number

// Глобальная функция для показа Toast (будет установлена через setToastHandler)
let globalShowToast: ToastHandler | null = null

/**
 * Устанавливает глобальный обработчик Toast уведомлений
 */
export function setToastHandler(showToast: ToastHandler): void {
  globalShowToast = showToast
}

/**
 * Функция для получения CSRF токена
 */
function getCsrfToken(): string | null {
  if (typeof document === 'undefined') {
    return null
  }
  // Пытаемся получить из meta тега
  const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
  if (metaToken) {
    return metaToken
  }
  // Если нет в meta, пытаемся получить из cookie (Laravel использует XSRF-TOKEN)
  const cookies = document.cookie.split(';')
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=')
    if (name === 'XSRF-TOKEN') {
      return decodeURIComponent(value)
    }
  }
  return null
}

/**
 * Создаем настроенный экземпляр axios с единой конфигурацией
 */
const apiClient: AxiosInstance = axios.create({
  headers: {
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  // Включаем отправку cookies для работы с Laravel сессиями
  withCredentials: true,
})

// Request interceptor для добавления префикса /api и CSRF токена
apiClient.interceptors.request.use(
  (config) => {
    // Если URL не начинается с /api/ или /settings/, и не является абсолютным URL, добавляем /api
    if (config.url && !config.url.startsWith('/api/') && !config.url.startsWith('/settings/') && !config.url.startsWith('http')) {
      config.url = `/api${config.url}`
    }
    
    // Добавляем CSRF токен для всех запросов (кроме GET)
    // Laravel требует CSRF токен для POST, PUT, PATCH, DELETE запросов
    const method = config.method?.toUpperCase()
    if (method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrfToken = getCsrfToken()
      if (csrfToken) {
        const headers = (config.headers ?? {}) as AxiosRequestHeaders
        headers['X-CSRF-TOKEN'] = csrfToken
        config.headers = headers
      }
    }
    
    // Также добавляем CSRF токен для GET запросов, если он нужен для аутентификации
    // (некоторые API endpoints могут требовать его для проверки сессии)
    if (method === 'GET') {
      const csrfToken = getCsrfToken()
      if (csrfToken && !config.headers?.['X-CSRF-TOKEN']) {
        const headers = (config.headers ?? {}) as AxiosRequestHeaders
        headers['X-CSRF-TOKEN'] = csrfToken
        config.headers = headers
      }
    }
    
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor для обработки ошибок и логирования
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Игнорируем отмененные запросы (Inertia.js)
    // Это нормальное поведение при навигации - не логируем как ошибку
    if (error?.code === 'ERR_CANCELED' || 
        error?.name === 'CanceledError' || 
        error?.message === 'canceled' ||
        error?.message === 'Request aborted') {
      // Не логируем отмененные запросы - это нормальное поведение Inertia.js
      return Promise.reject(error)
    }

    const message = error.response?.data?.message || error.message || ERROR_MESSAGES.UNKNOWN
    const status = error.response?.status
    const url = error.config?.url || '(unknown url)'
    const method = (error.config?.method || 'GET').toUpperCase()
    const data = error.response?.data
    
    // 401 - не показываем Toast и не логируем постоянно, обычно это обрабатывается на уровне auth
    // 422 с "Not enough data" - это не ошибка, а нормальное состояние (недостаточно данных для прогноза)
    // Множественные 401 могут происходить из-за интервалов обновления
    const isNotEnoughData = status === 422 && (
      message.includes('Not enough data') || 
      message.includes('недостаточно данных') ||
      message.includes('Failed to generate prediction')
    )
    
    // Не логируем как ERROR, если это "Not enough data" - это нормальное состояние
    if (isNotEnoughData) {
      logger.debug('[apiClient] Not enough data for prediction (normal state)', {
        url,
        status,
        message,
      })
      return Promise.reject(error)
    }
    
    // Логируем ошибку (но не логируем 401 постоянно, чтобы не засорять консоль)
    if (status !== 401) {
      logger.error('[HTTP ERROR]', { method, url, status, data, message, error })
    }
    
    if (globalShowToast && status !== 401 && !isNotEnoughData) {
      globalShowToast(`Ошибка: ${message}`, 'error', 5000)
    }
    
    return Promise.reject(error)
  }
)

// Экспортируем единый экземпляр apiClient
export default apiClient

// Экспортируем типы для удобства
export type { AxiosInstance, AxiosRequestConfig }
