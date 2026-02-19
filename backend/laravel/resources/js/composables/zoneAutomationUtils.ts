/**
 * Shared utility functions for zone automation composables.
 * Keep this file free of Vue reactivity imports.
 */

export type AutomationLogicMode = 'setup' | 'working'

export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value === 'string') {
    const normalized = value.trim()
    if (normalized === '') return null

    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

export function normalizeAutomationLogicMode(
  value: unknown,
  fallback: AutomationLogicMode = 'working'
): AutomationLogicMode {
  return value === 'setup' ? 'setup' : value === 'working' ? 'working' : fallback
}

export function normalizeIsoInput(rawValue: string): string {
  const raw = rawValue.trim()
  if (!raw) return raw

  const hasTimezone = /(?:Z|z|[+-]\d{2}:\d{2})$/.test(raw)
  const looksIsoDateTime = /^\d{4}-\d{2}-\d{2}T/.test(raw)
  if (looksIsoDateTime && !hasTimezone) {
    return `${raw}Z`
  }
  return raw
}

export function parseIsoDate(value: string | null | undefined): Date | null {
  const raw = normalizeIsoInput(String(value ?? ''))
  if (!raw) return null
  const parsed = new Date(raw)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatRelativeMs(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes <= 0) return `${seconds}с`
  if (minutes < 60) return `${minutes}м ${seconds}с`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return `${hours}ч ${restMinutes}м`
}
