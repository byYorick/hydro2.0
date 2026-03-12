/**
 * Composable для централизованной обработки ошибок
 */
import { ref, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ERROR_MESSAGES, getErrorMessageByStatus } from '@/constants/messages'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastHandler } from './useApi'

/**
 * Типизированные классы ошибок
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public data?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

export class NetworkError extends Error {
  constructor(message: string, public originalError?: unknown) {
    super(message)
    this.name = 'NetworkError'
    Object.setPrototypeOf(this, NetworkError.prototype)
  }
}

export class ValidationError extends Error {
  constructor(
    message: string,
    public errors: Record<string, string[]>
  ) {
    super(message)
    this.name = 'ValidationError'
    Object.setPrototypeOf(this, ValidationError.prototype)
  }
}

export type AppError = ApiError | NetworkError | ValidationError | Error

/**
 * Интерфейс для контекста ошибки
 */
export interface ErrorContext {
  component?: string
  action?: string
  [key: string]: unknown
}

/**
 * Composable для обработки ошибок
 */
export function useErrorHandler(showToast?: ToastHandler) {
  const lastError: Ref<AppError | null> = ref(null)
  const errorContext: Ref<ErrorContext | null> = ref(null)

  /**
   * Преобразует неизвестную ошибку в типизированную
   */
  function normalizeError(error: unknown): AppError {
    // Axios ошибки
    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as {
        response?: {
          status?: number
          data?: {
            message?: string
            errors?: Record<string, string[]>
            code?: string
          }
        }
        message?: string
      }

      const status = axiosError.response?.status || 500
      const responseData = axiosError.response?.data
      const message = responseData?.message || axiosError.message || ERROR_MESSAGES.UNKNOWN

      // Ошибки валидации (422)
      if (status === 422 && responseData?.errors) {
        return new ValidationError(message, responseData.errors)
      }

      return new ApiError(
        message,
        status,
        responseData?.code,
        responseData
      )
    }

    // Network ошибки
    if (error && typeof error === 'object' && 'code' in error) {
      const code = (error as { code?: string }).code
      if (code === 'ERR_NETWORK' || code === 'ECONNABORTED') {
        return new NetworkError(
          ERROR_MESSAGES.NETWORK,
          error
        )
      }
    }

    // Обычные Error объекты
    if (error instanceof Error) {
      return error
    }

    // Строки
    if (typeof error === 'string') {
      return new Error(error)
    }

    // Остальное
    return new Error(ERROR_MESSAGES.UNKNOWN)
  }

  /**
   * Очищает контекст от потенциальных циклических ссылок
   */
  function sanitizeContext(context?: ErrorContext): ErrorContext | undefined {
    if (!context) return undefined
    
    const sanitized: ErrorContext = {}
    for (const key in context) {
      if (Object.prototype.hasOwnProperty.call(context, key)) {
        const value = context[key]
        // Пропускаем сложные объекты, которые могут содержать циклические ссылки
        if (value === null || value === undefined) {
          sanitized[key] = value
        } else if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
          sanitized[key] = value
        } else if (Array.isArray(value)) {
          // Для массивов конвертируем в строку, если содержит сложные объекты
          sanitized[key] = value.map(item => 
            typeof item === 'object' && item !== null ? '[Object]' : item
          )
        } else if (typeof value === 'object') {
          // Для объектов сохраняем только простые свойства
          sanitized[key] = '[Object]'
        } else {
          sanitized[key] = String(value)
        }
      }
    }
    return sanitized
  }

  /**
   * Обрабатывает ошибку с контекстом
   */
  function handleError(
    error: unknown,
    context?: ErrorContext
  ): AppError {
    const normalizedError = normalizeError(error)
    lastError.value = normalizedError
    errorContext.value = context || null

    // Очищаем контекст от циклических ссылок
    const safeContext = sanitizeContext(context)

    // Логирование
    if (normalizedError instanceof ApiError) {
      logger.error('[ApiError]', {
        message: normalizedError.message,
        status: normalizedError.status,
        code: normalizedError.code,
        context: safeContext,
      })
    } else if (normalizedError instanceof NetworkError) {
      logger.error('[NetworkError]', {
        message: normalizedError.message,
        context: safeContext,
        originalError: normalizedError.originalError instanceof Error ? {
          message: normalizedError.originalError.message,
          name: normalizedError.originalError.name,
        } : normalizedError.originalError,
      })
    } else if (normalizedError instanceof ValidationError) {
      logger.warn('[ValidationError]', {
        message: normalizedError.message,
        errors: normalizedError.errors,
        context: safeContext,
      })
    } else {
      logger.error('[Error]', {
        message: normalizedError.message,
        errorName: normalizedError.name,
        errorStack: normalizedError.stack?.split('\n').slice(0, 5).join('\n'),
        context: safeContext,
      }, normalizedError)
    }

    // Показ Toast уведомления
    if (showToast) {
      let toastMessage = normalizedError.message
      let toastVariant: 'error' | 'warning' = 'error'

      if (normalizedError instanceof NetworkError) {
        toastMessage = 'Ошибка сети. Проверьте подключение.'
        toastVariant = 'error'
      } else if (normalizedError instanceof ValidationError) {
        toastMessage = ERROR_MESSAGES.VALIDATION
        toastVariant = 'warning'
      } else if (normalizedError instanceof ApiError) {
        if (normalizedError.status === 401) {
          toastMessage = ERROR_MESSAGES.UNAUTHORIZED
        } else if (normalizedError.status === 403) {
          toastMessage = ERROR_MESSAGES.FORBIDDEN
        } else if (normalizedError.status === 404) {
          toastMessage = ERROR_MESSAGES.NOT_FOUND
        } else if (normalizedError.status >= 500) {
          toastMessage = 'Ошибка сервера. Попробуйте позже.'
        } else {
          toastMessage = normalizedError.message
        }
        toastVariant = 'error'
      }

      showToast(toastMessage, toastVariant, TOAST_TIMEOUT.LONG)
    }

    return normalizedError
  }

  /**
   * Очищает последнюю ошибку
   */
  function clearError(): void {
    lastError.value = null
    errorContext.value = null
  }

  /**
   * Проверяет, является ли ошибка определенного типа
   */
  function isErrorType<T extends AppError>(
    error: AppError,
    errorClass: new (...args: never[]) => T
  ): error is T {
    return error instanceof errorClass
  }

  return {
    handleError,
    clearError,
    isErrorType,
    lastError: lastError as Readonly<Ref<AppError | null>>,
    errorContext: errorContext as Readonly<Ref<ErrorContext | null>>,
  }
}

