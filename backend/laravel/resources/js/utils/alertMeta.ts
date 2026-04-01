import { resolveAlertCodeMeta } from '@/constants/alertErrorMap'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import type { Alert } from '@/types/Alert'

export type NormalizedAlertStatus = 'ACTIVE' | 'RESOLVED' | 'OTHER'
export type NormalizedAlertSeverity = 'critical' | 'error' | 'warning' | 'info' | 'other'

export function normalizeAlertStatus(status: Alert['status'] | string | undefined | null): NormalizedAlertStatus {
  const normalized = String(status ?? '').trim().toUpperCase()
  if (normalized === 'ACTIVE') return 'ACTIVE'
  if (normalized === 'RESOLVED') return 'RESOLVED'
  return 'OTHER'
}

export function normalizeAlertSeverity(severity: Alert['severity'] | string | undefined | null): NormalizedAlertSeverity {
  const normalized = String(severity ?? '').trim().toLowerCase()
  if (normalized === 'critical') return 'critical'
  if (normalized === 'error') return 'error'
  if (normalized === 'warning') return 'warning'
  if (normalized === 'info') return 'info'
  return 'other'
}

export function detailsToString(details: Alert['details']): string {
  if (!details || typeof details !== 'object') return ''
  try {
    return JSON.stringify(details)
  } catch {
    return ''
  }
}

export function getAlertMeta(alert?: Alert | null) {
  const details = alert?.details as Record<string, unknown> | null | undefined

  if (alert?.title || alert?.description || alert?.recommendation) {
    return {
      title: String(alert.title || 'Системное предупреждение'),
      description: String(alert.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
      recommendation: String(alert.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
    }
  }

  if (details?.title || details?.description || details?.recommendation) {
    return {
      title: String(details.title || 'Системное предупреждение'),
      description: String(details.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
      recommendation: String(details.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
    }
  }

  return resolveAlertCodeMeta(alert?.code)
}

export function getAlertTitle(alert: Alert): string {
  return getAlertMeta(alert).title || alert.type || 'Системное предупреждение'
}

export function getAlertDescription(alert: Alert): string {
  return getAlertMeta(alert).description || ''
}

export function getAlertRecommendation(alert: Alert): string {
  return getAlertMeta(alert).recommendation || ''
}

export function getAlertMessage(alert: Alert): string {
  const details = alert.details as Record<string, unknown> | null | undefined
  const rawMessage = String(
    alert.message
      || details?.message
      || details?.reason
      || details?.error
      || details?.error_message
      || '',
  ).trim()

  const localized = resolveHumanErrorMessage({
    code: String(details?.error_code || alert.code || '').trim() || null,
    message: rawMessage || null,
  })

  return localized || rawMessage
}

export function formatAlertDate(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

export function alertBadgeVariant(
  status: Alert['status'] | string | undefined,
): 'danger' | 'success' | 'warning' {
  const normalized = normalizeAlertStatus(status)
  if (normalized === 'ACTIVE') return 'danger'
  if (normalized === 'RESOLVED') return 'success'
  return 'warning'
}

export function severityRailClass(alert: Alert): string {
  if (normalizeAlertStatus(alert.status) === 'RESOLVED') return 'bg-[color:var(--accent-green)]'

  const severity = normalizeAlertSeverity(alert.severity)
  if (severity === 'critical') return 'bg-[color:var(--accent-red)]'
  if (severity === 'error') return 'bg-[color:var(--accent-amber)]'
  if (severity === 'warning') return 'bg-[color:var(--accent-amber)]'
  if (severity === 'info') return 'bg-[color:var(--accent-cyan)]'
  return 'bg-[color:var(--text-muted)]'
}

