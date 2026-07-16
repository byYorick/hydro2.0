export type AlertPreviewSeverity = 'critical' | 'error' | 'warning' | 'info'

/**
 * Severity для превью алерта на карточке зоны.
 * Приоритет: backend `severity` → эвристика по `type` → warning.
 */
export function resolveAlertPreviewSeverity(
  severity?: string | null,
  type?: string | null,
): AlertPreviewSeverity {
  const fromSeverity = String(severity ?? '').trim().toLowerCase()
  if (
    fromSeverity === 'critical'
    || fromSeverity === 'error'
    || fromSeverity === 'warning'
    || fromSeverity === 'info'
  ) {
    return fromSeverity
  }

  const lower = String(type ?? '').toLowerCase()
  if (lower.includes('critical')) return 'critical'
  if (lower.includes('error') || lower.includes('alarm') || lower.includes('fail')) return 'error'
  if (lower.includes('info')) return 'info'
  if (lower.includes('warn') || lower.includes('degraded') || lower.includes('stale')) return 'warning'
  return 'warning'
}
