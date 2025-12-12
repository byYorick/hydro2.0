/**
 * Единый модуль конфигурации HTTP клиента (axios)
 * Все настройки CSRF, baseURL, interceptors централизованы здесь
 */
import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { logger } from './logger'
import { ERROR_MESSAGES } from '@/constants/messages'

// Тип функции для показа Toast
export type ToastHandler = (message: string, variant?: string, duration?: number) => void

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
        config.headers = config.headers || {}
        config.headers['X-CSRF-TOKEN'] = csrfToken
      }
    }
    
    // Также добавляем CSRF токен для GET запросов, если он нужен для аутентификации
    // (некоторые API endpoints могут требовать его для проверки сессии)
    if (method === 'GET') {
      const csrfToken = getCsrfToken()
      if (csrfToken && !config.headers?.['X-CSRF-TOKEN']) {
        config.headers = config.headers || {}
        config.headers['X-CSRF-TOKEN'] = csrfToken
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
    
    // Логируем ошибку (но не логируем 401 постоянно, чтобы не засорять консоль)
    if (status !== 401) {
      logger.error('[HTTP ERROR]', { method, url, status, data, message, error })
    }
    
    // 401 - не показываем Toast и не логируем постоянно, обычно это обрабатывается на уровне auth
    // Множественные 401 могут происходить из-за интервалов обновления
    if (globalShowToast && status !== 401) {
      globalShowToast(`Ошибка: ${message}`, 'error', 5000)
    }
    
    return Promise.reject(error)
  }
)

// Экспортируем единый экземпляр apiClient
export default apiClient

// Экспортируем типы для удобства
export type { AxiosInstance, AxiosRequestConfig }

