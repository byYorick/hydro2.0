/**
 * Единый словарь тонов статуса.
 *
 * Семантика: ok / warning / critical / offline / info / neutral.
 * Имена Hydroflow (`growth`, `warn`, `alert`, `brand`) остаются алиасами,
 * но Chip рисует их прежними классами, чтобы launch/cockpit не сменили цвет.
 */

export const STATUS_TONES = ['ok', 'warning', 'critical', 'offline', 'info', 'neutral'] as const

export type StatusTone = (typeof STATUS_TONES)[number]

export type LegacyChipTone = 'brand' | 'growth' | 'warn' | 'alert'

export type ChipTone = StatusTone | LegacyChipTone

export const STATUS_COLOR_VAR: Record<StatusTone, string> = {
  ok: 'var(--status-ok)',
  warning: 'var(--status-warning)',
  critical: 'var(--status-critical)',
  offline: 'var(--status-offline)',
  info: 'var(--status-info)',
  neutral: 'var(--text-dim)',
}

const LEGACY_CHIP_CLASS: Record<LegacyChipTone | 'neutral', string> = {
  neutral: 'bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-muted)]',
  brand: 'bg-brand-soft text-brand-ink border-brand-soft',
  growth: 'bg-growth-soft text-growth border-growth-soft',
  warn: 'bg-warn-soft text-warn border-warn-soft',
  alert: 'bg-alert-soft text-alert border-alert-soft',
}

const STATUS_PILL_CLASS: Record<StatusTone, string> = {
  ok: 'status-chip--running',
  warning: 'status-chip--warning',
  critical: 'status-chip--alarm',
  offline: 'status-chip--offline',
  info: 'status-chip--paused',
  neutral: 'badge--neutral',
}

const BADGE_CLASS: Record<string, string> = {
  success: 'badge--success',
  ok: 'badge--ok',
  warning: 'badge--warning',
  danger: 'badge--danger',
  critical: 'badge--critical',
  info: 'badge--info',
  offline: 'badge--offline',
  neutral: 'badge--neutral',
  secondary: 'badge--secondary',
}

export function canonicalStatusTone(tone: string | null | undefined): StatusTone {
  switch (tone) {
    case 'ok':
    case 'success':
    case 'growth':
      return 'ok'
    case 'warning':
    case 'warn':
      return 'warning'
    case 'critical':
    case 'danger':
    case 'alert':
      return 'critical'
    case 'offline':
      return 'offline'
    case 'info':
    case 'brand':
      return 'info'
    default:
      return 'neutral'
  }
}

export function isLegacyChipTone(tone: string | null | undefined): tone is LegacyChipTone {
  return tone === 'brand' || tone === 'growth' || tone === 'warn' || tone === 'alert'
}

/** Класс Chip: исторические имена не меняют вёрстку launch-экранов. */
export function chipToneClass(tone: ChipTone | null | undefined): string {
  if (!tone || tone === 'neutral') {
    return LEGACY_CHIP_CLASS.neutral
  }
  if (isLegacyChipTone(tone)) {
    return LEGACY_CHIP_CLASS[tone]
  }
  return `tone-${canonicalStatusTone(tone)}`
}

export function statusPillClass(tone: StatusTone | string | null | undefined): string {
  return STATUS_PILL_CLASS[canonicalStatusTone(tone)]
}

export function badgeVariantClass(variant: string | null | undefined): string {
  if (!variant) {
    return BADGE_CLASS.neutral
  }
  return BADGE_CLASS[variant] ?? BADGE_CLASS.neutral
}
