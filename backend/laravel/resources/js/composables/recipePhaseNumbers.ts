export function toNullableNumber(value: unknown, fallback: number | null = null): number | null {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

/** Пустая строка и пробелы — null. Number('') равен 0, для порогов культуры это включение контура. */
export function nullableDraftNumber(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  const text = String(value).trim()
  if (text === '') {
    return null
  }
  const parsed = Number(text)
  return Number.isFinite(parsed) ? parsed : null
}

export function nullableDraftInt(value: unknown): number | null {
  const parsed = nullableDraftNumber(value)
  if (parsed === null) {
    return null
  }
  return Math.round(parsed)
}

export function toNullableInt(value: unknown, fallback: number | null = null): number | null {
  const parsed = toNullableNumber(value, fallback)
  if (parsed === null) {
    return null
  }

  return Math.round(parsed)
}

export function normalizeTimeString(value: unknown, fallback = '06:00:00'): string {
  const normalized = String(value ?? '').trim()
  if (/^\d{2}:\d{2}:\d{2}$/.test(normalized)) {
    return normalized
  }

  if (/^\d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`
  }

  return fallback
}
