import { resolveHumanErrorMessage } from '@/utils/errorCatalog'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object') {
    return value as Record<string, unknown>
  }
  return null
}

export function pickApiMessageFromPayload(data: Record<string, unknown> | null): string | null {
  if (!data) {
    return null
  }
  const keys = ['message', 'error', 'detail', 'details'] as const
  for (const key of keys) {
    const value = data[key]
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim()
    }
  }
  return null
}

function firstValidationError(errors: unknown): string | null {
  const record = asRecord(errors)
  if (!record) {
    return null
  }

  for (const value of Object.values(record)) {
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
      return value[0]
    }
    if (typeof value === 'string' && value.trim().length > 0) {
      return value
    }
  }

  return null
}

export function extractHumanErrorMessage(error: unknown, fallback = 'Произошла ошибка'): string {
  const record = asRecord(error)
  const response = asRecord(record?.response)
  const data = asRecord(response?.data)
  const status = typeof response?.status === 'number' ? response.status : null

  const validation = firstValidationError(data?.errors)
  if (validation) {
    return validation
  }

  const apiMessage = pickApiMessageFromPayload(data)
  const apiCode = typeof data?.code === 'string' ? data.code : null
  const localizedApiMessage = resolveHumanErrorMessage({
    code: apiCode,
    message: apiMessage,
  })
  if (localizedApiMessage) {
    return localizedApiMessage
  }

  if (status === 403) {
    return 'Недостаточно прав для выполнения действия'
  }
  if (status === 404) {
    return 'Запрошенный ресурс не найден'
  }
  if (status === 419) {
    return 'Сессия устарела. Обновите страницу и повторите действие.'
  }
  if (status === 422) {
    return 'Ошибка валидации данных'
  }
  if (status !== null && status >= 500) {
    return 'Ошибка сервера. Попробуйте позже'
  }

  const message = record?.message
  if (typeof message === 'string' && message.trim().length > 0) {
    return message
  }

  return fallback
}
