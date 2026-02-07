function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object') {
    return value as Record<string, unknown>
  }
  return null
}

function firstValidationMessage(errors: unknown): string | null {
  const errorsRecord = asRecord(errors)
  if (!errorsRecord) {
    return null
  }

  for (const value of Object.values(errorsRecord)) {
    if (Array.isArray(value) && value.length > 0) {
      const first = value[0]
      if (typeof first === 'string' && first.trim().length > 0) {
        return first
      }
    }
    if (typeof value === 'string' && value.trim().length > 0) {
      return value
    }
  }

  return null
}

function normalizeReadinessErrors(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim())
}

export function extractSetupWizardErrorDetails(error: unknown): string[] {
  const errorRecord = asRecord(error)
  const response = asRecord(errorRecord?.response)
  const data = asRecord(response?.data)
  const details: string[] = []

  for (const readinessError of normalizeReadinessErrors(data?.readiness_errors)) {
    details.push(readinessError)
  }

  const detailsField = data?.details
  if (typeof detailsField === 'string' && detailsField.trim().length > 0) {
    details.push(detailsField.trim())
  }

  const nestedData = asRecord(data?.data)
  const nestedErrors = nestedData?.errors
  if (Array.isArray(nestedErrors)) {
    for (const entry of nestedErrors) {
      const record = asRecord(entry)
      const message = record?.message
      if (typeof message === 'string' && message.trim().length > 0) {
        details.push(message.trim())
      }
    }
  }

  return [...new Set(details)]
}

export function extractSetupWizardErrorMessage(error: unknown, fallback: string): string {
  const errorRecord = asRecord(error)
  const response = asRecord(errorRecord?.response)
  const data = asRecord(response?.data)

  const validation = firstValidationMessage(data?.errors)
  if (validation) {
    return validation
  }

  const responseMessage = data?.message
  if (typeof responseMessage === 'string' && responseMessage.trim().length > 0) {
    return responseMessage
  }

  const directMessage = errorRecord?.message
  if (typeof directMessage === 'string' && directMessage.trim().length > 0) {
    return directMessage
  }

  return fallback
}
