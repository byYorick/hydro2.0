import type { Alert } from '@/types/Alert'

type AlertLike = Pick<Alert, 'details'> | { details?: Record<string, unknown> | null }

function detailsRecord(alert: AlertLike | null | undefined): Record<string, unknown> | null {
  const details = alert?.details
  if (!details || typeof details !== 'object' || Array.isArray(details)) {
    return null
  }

  return details
}

function pickDetailString(details: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = details[key]
    if (value === null || value === undefined || value === '') {
      continue
    }

    return String(value)
  }

  return null
}

export function getAlertTaskId(alert: AlertLike | null | undefined): string | null {
  const details = detailsRecord(alert)
  if (!details) {
    return null
  }

  return pickDetailString(details, ['task_id', 'ae_task_id', 'automation_task_id'])
}

export function getAlertCorrectionWindowId(alert: AlertLike | null | undefined): string | null {
  const details = detailsRecord(alert)
  if (!details) {
    return null
  }

  return pickDetailString(details, ['correction_window_id'])
}

export function getAlertDetailsContextSummary(alert: AlertLike | null | undefined): string | null {
  const details = detailsRecord(alert)
  if (!details) {
    return null
  }

  const parts: string[] = []
  const errorCode = pickDetailString(details, ['error_code'])
  const stage = pickDetailString(details, ['stage'])

  if (errorCode) {
    parts.push(`error: ${errorCode}`)
  }

  if (stage) {
    parts.push(`stage: ${stage}`)
  }

  return parts.length > 0 ? parts.join(' · ') : null
}

export function zoneAlertsTabUrl(zoneId: number): string {
  return `/zones/${zoneId}?tab=alerts`
}
