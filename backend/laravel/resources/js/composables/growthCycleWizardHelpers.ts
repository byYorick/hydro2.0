/**
 * Чистые helper-функции для GrowthCycleWizard.
 *
 * Вынесены из useGrowthCycleWizard.ts, чтобы разгрузить основной composable
 * и облегчить unit-тестирование независимых utility-функций.
 */

import { clamp, isValidHHMM, toFiniteNumber } from '@/services/automation/parsingUtils'

export { clamp, isValidHHMM, toFiniteNumber }

export interface WizardFormState {
  zoneId: number | null
  startedAt: string
  expectedHarvestAt: string
}

export interface ZoneNodeResponse {
  id?: number
  uid?: string
  name?: string
  channels?: Array<Record<string, unknown>>
}

export interface PaginatedCollectionPayload<T> {
  items: T[]
  currentPage: number | null
  lastPage: number | null
}

export function getNowLocalDatetimeValue(): string {
  const now = new Date()
  const offsetMs = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 16)
}

export function createDefaultForm(zoneId?: number): WizardFormState {
  return {
    zoneId: zoneId || null,
    startedAt: getNowLocalDatetimeValue(),
    expectedHarvestAt: '',
  }
}

export function normalizeDatetimeLocal(value: string | null | undefined): string | null {
  if (!value) {
    return null
  }

  const raw = value.trim()
  if (!raw) {
    return null
  }

  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw)) {
    return raw
  }

  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }

  return parsed.toISOString().slice(0, 16)
}

export function addHoursToTime(start: string, hours: number): string {
  const [h, m] = (isValidHHMM(start) ? start : '06:00').split(':').map(Number)
  const startMinutes = h * 60 + m
  const delta = Math.round(clamp(hours, 0, 24) * 60)
  const totalMinutes = (startMinutes + delta) % (24 * 60)
  const endH = Math.floor(totalMinutes / 60)
    .toString()
    .padStart(2, '0')
  const endM = (totalMinutes % 60).toString().padStart(2, '0')
  return `${endH}:${endM}`
}

export function extractNodesFromResponse(raw: unknown): ZoneNodeResponse[] {
  if (Array.isArray(raw)) {
    return raw as ZoneNodeResponse[]
  }

  if (raw && typeof raw === 'object') {
    const payload = raw as {
      data?: unknown
    }

    if (Array.isArray(payload.data)) {
      return payload.data as ZoneNodeResponse[]
    }

    if (payload.data && typeof payload.data === 'object') {
      const nested = payload.data as { data?: unknown }
      if (Array.isArray(nested.data)) {
        return nested.data as ZoneNodeResponse[]
      }
    }
  }

  return []
}

export function extractCollectionItems<T>(raw: unknown): T[] {
  return extractPaginatedCollection<T>(raw).items
}

export function extractPaginatedCollection<T>(raw: unknown): PaginatedCollectionPayload<T> {
  if (Array.isArray(raw)) {
    return {
      items: raw as T[],
      currentPage: null,
      lastPage: null,
    }
  }

  if (!raw || typeof raw !== 'object') {
    return {
      items: [],
      currentPage: null,
      lastPage: null,
    }
  }

  const payload = raw as { data?: unknown }
  if (Array.isArray(payload.data)) {
    return {
      items: payload.data as T[],
      currentPage: null,
      lastPage: null,
    }
  }

  if (payload.data && typeof payload.data === 'object') {
    const nested = payload.data as {
      data?: unknown
      current_page?: unknown
      last_page?: unknown
    }
    if (Array.isArray(nested.data)) {
      return {
        items: nested.data as T[],
        currentPage: toFiniteNumber(nested.current_page),
        lastPage: toFiniteNumber(nested.last_page),
      }
    }
  }

  return {
    items: [],
    currentPage: null,
    lastPage: null,
  }
}

export function formatDateTime(dateString: string): string {
  if (!dateString) return '—'
  try {
    return new Date(dateString).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateString
  }
}

export function formatDate(dateString: string): string {
  if (!dateString) return '—'
  try {
    return new Date(dateString).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return dateString
  }
}
