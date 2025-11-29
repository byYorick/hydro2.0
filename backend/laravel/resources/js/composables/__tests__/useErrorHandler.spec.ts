import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useErrorHandler, ApiError, NetworkError, ValidationError } from '../useErrorHandler'

describe('useErrorHandler', () => {
  let mockShowToast: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockShowToast = vi.fn()
    vi.clearAllMocks()
  })

  describe('normalizeError', () => {
    it('should normalize ApiError from axios error', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 404,
          data: {
            message: 'Not found',
            code: 'NOT_FOUND'
          }
        },
        message: 'Request failed'
      }

      const error = handleError(axiosError)
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).status).toBe(404)
      expect((error as ApiError).code).toBe('NOT_FOUND')
      expect((error as ApiError).message).toBe('Not found')
    })

    it('should normalize ValidationError from 422 status', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 422,
          data: {
            message: 'Validation failed',
            errors: {
              email: ['Invalid email'],
              password: ['Too short']
            }
          }
        }
      }

      const error = handleError(axiosError)
      expect(error).toBeInstanceOf(ValidationError)
      expect((error as ValidationError).errors).toEqual({
        email: ['Invalid email'],
        password: ['Too short']
      })
    })

    it('should normalize NetworkError from network errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const networkError = {
        code: 'ERR_NETWORK',
        message: 'Network error'
      }

      const error = handleError(networkError)
      expect(error).toBeInstanceOf(NetworkError)
      expect((error as NetworkError).message).toContain('Ошибка сети')
    })

    it('should normalize regular Error objects', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const regularError = new Error('Regular error')

      const error = handleError(regularError)
      expect(error).toBeInstanceOf(Error)
      expect(error.message).toBe('Regular error')
    })

    it('should normalize string errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const stringError = 'String error'

      const error = handleError(stringError)
      expect(error).toBeInstanceOf(Error)
      expect(error.message).toBe('String error')
    })

    it('should normalize unknown errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const unknownError = { some: 'object' }

      const error = handleError(unknownError)
      expect(error).toBeInstanceOf(Error)
      expect(error.message).toBe('Произошла неизвестная ошибка.')
    })
  })

  describe('handleError', () => {
    it('should log and show toast for ApiError', () => {
      const { handleError, lastError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 500,
          data: { message: 'Server error' }
        }
      }

      handleError(axiosError, { component: 'TestComponent' })

      expect(lastError.value).toBeInstanceOf(ApiError)
      expect(mockShowToast).toHaveBeenCalledWith(
        'Ошибка сервера. Попробуйте позже.',
        'error',
        5000
      )
    })

    it('should handle 401 errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 401,
          data: { message: 'Unauthorized' }
        }
      }

      handleError(axiosError)

      expect(mockShowToast).toHaveBeenCalledWith(
        'Требуется авторизация. Пожалуйста, войдите в систему.',
        'error',
        5000
      )
    })

    it('should handle 403 errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 403,
          data: { message: 'Forbidden' }
        }
      }

      handleError(axiosError)

      expect(mockShowToast).toHaveBeenCalledWith(
        'Доступ запрещен. У вас нет прав для выполнения этого действия.',
        'error',
        5000
      )
    })

    it('should handle 404 errors', () => {
      const { handleError } = useErrorHandler(mockShowToast)
      const axiosError = {
        response: {
          status: 404,
          data: { message: 'Not found' }
        }
      }

      handleError(axiosError)

      expect(mockShowToast).toHaveBeenCalledWith(
        'Ресурс не найден.',
        'error',
        5000
      )
    })

    it('should handle NetworkError', () => {
      const { handleError, lastError } = useErrorHandler(mockShowToast)
      const networkError = { code: 'ERR_NETWORK' }

      handleError(networkError)

      expect(lastError.value).toBeInstanceOf(NetworkError)
      expect(mockShowToast).toHaveBeenCalledWith(
        'Ошибка сети. Проверьте подключение.',
        'error',
        5000
      )
    })

    it('should handle ValidationError with warning', () => {
      const { handleError, lastError } = useErrorHandler(mockShowToast)
      const validationError = {
        response: {
          status: 422,
          data: {
            message: 'Validation failed',
            errors: { field: ['Error message'] }
          }
        }
      }

      handleError(validationError)

      expect(lastError.value).toBeInstanceOf(ValidationError)
      expect(mockShowToast).toHaveBeenCalledWith(
        'Ошибка валидации. Проверьте введенные данные.',
        'warning',
        5000
      )
    })

    it('should save error context', () => {
      const { handleError, errorContext } = useErrorHandler(mockShowToast)
      const testContext = { component: 'TestComponent', action: 'testAction' }

      handleError(new Error('Test'), testContext)

      expect(errorContext.value).toEqual(testContext)
    })

    it('should work without showToast', () => {
      const { handleError, lastError } = useErrorHandler()
      const error = new Error('Test error')

      handleError(error)

      expect(lastError.value).toBeInstanceOf(Error)
      expect(lastError.value?.message).toBe('Test error')
    })
  })

  describe('clearError', () => {
    it('should clear last error and context', () => {
      const { handleError, clearError, lastError, errorContext } = useErrorHandler(mockShowToast)

      handleError(new Error('Test'), { component: 'Test' })
      expect(lastError.value).not.toBeNull()
      expect(errorContext.value).not.toBeNull()

      clearError()
      expect(lastError.value).toBeNull()
      expect(errorContext.value).toBeNull()
    })
  })

  describe('isErrorType', () => {
    it('should check if error is of specific type', () => {
      const { handleError, isErrorType } = useErrorHandler()
      const axiosError = {
        response: {
          status: 404,
          data: { message: 'Not found' }
        }
      }

      const error = handleError(axiosError)
      expect(isErrorType(error, ApiError)).toBe(true)
      expect(isErrorType(error, NetworkError)).toBe(false)
    })
  })
})

