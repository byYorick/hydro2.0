function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object') {
    return value as Record<string, unknown>
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

  const apiMessage = data?.message
  if (typeof apiMessage === 'string' && apiMessage.trim().length > 0) {
    return apiMessage
  }

  if (status === 403) {
    return 'Недостаточно прав для выполнения действия'
  }
  if (status === 404) {
    return 'Запрошенный ресурс не найден'
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
