import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { classifyEventKind } from '@/utils/i18n'
import type { ZoneEvent } from '@/types/ZoneEvent'
import type { BadgeVariant } from '@/Components/Badge.vue'

export function toPayloadRecord(payload: unknown): Record<string, unknown> | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
  return payload as Record<string, unknown>
}

export function hasExpandablePayload(event: ZoneEvent): boolean {
  const payload = toPayloadRecord(event.payload)
  return payload !== null && Object.keys(payload).length > 0
}

export function readNumber(payload: Record<string, unknown> | null, key: string): number | null {
  if (!payload) return null
  const raw = payload[key]
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string' && raw.trim() !== '') {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

export function readString(payload: Record<string, unknown> | null, key: string): string | null {
  if (!payload) return null
  const raw = payload[key]
  if (typeof raw === 'string' && raw.trim() !== '') return raw
  if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
  return null
}

export function firstNumber(payload: Record<string, unknown> | null, keys: string[]): number | null {
  for (const key of keys) {
    const value = readNumber(payload, key)
    if (value !== null) return value
  }
  return null
}

export function firstString(payload: Record<string, unknown> | null, keys: string[]): string | null {
  for (const key of keys) {
    const value = readString(payload, key)
    if (value !== null) return value
  }
  return null
}

export function formatPayloadNumber(value: number | null, digits = 3): string | null {
  if (value === null || !Number.isFinite(value)) return null
  return value.toFixed(digits)
}

export function boolLabel(value: unknown): string {
  if (value === true) return 'вкл'
  if (value === false) return 'выкл'
  return '—'
}

export function humanizeEventError(code?: string | null, message?: string | null): string | null {
  return resolveHumanErrorMessage({ code, message }, message ?? code ?? null)
}

export function getEventVariant(kind: string): BadgeVariant {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'danger'
  if (category === 'WARNING') return 'warning'
  if (category === 'INFO') return 'info'
  if (category === 'ACTION') return 'success'
  return 'neutral'
}

export function eventDotClass(kind: string): string {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'bg-[color:var(--accent-red)]'
  if (category === 'WARNING') return 'bg-[color:var(--accent-amber)]'
  if (category === 'INFO') return 'bg-[color:var(--accent-cyan)]'
  if (category === 'ACTION') return 'bg-[color:var(--accent-green)]'
  return 'bg-[color:var(--text-muted)]'
}
