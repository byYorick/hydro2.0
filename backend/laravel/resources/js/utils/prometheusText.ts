/**
 * Извлекает scalar gauge/counter без labels из Prometheus text exposition.
 */
export function parsePrometheusScalar(text: string, metricName: string): number | null {
  const escaped = metricName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pattern = new RegExp(`^${escaped}(?:\\{[^}]*\\})?\\s+(-?[\\d.eE+-]+)\\s*$`, 'm')
  const match = text.match(pattern)
  if (!match?.[1]) {
    return null
  }
  const value = Number(match[1])
  return Number.isFinite(value) ? value : null
}

export interface SchedulerDispatchMetricsSnapshot {
  pendingIntents: number | null
  oldestPendingAgeSec: number | null
  dispatchCycleOverrunSec: number | null
}

export function parseSchedulerDispatchMetrics(text: string): SchedulerDispatchMetricsSnapshot {
  return {
    pendingIntents: parsePrometheusScalar(text, 'laravel_scheduler_pending_intents_count'),
    oldestPendingAgeSec: parsePrometheusScalar(text, 'laravel_scheduler_oldest_pending_intent_age_seconds'),
    dispatchCycleOverrunSec: parsePrometheusScalar(text, 'laravel_scheduler_dispatch_cycle_overrun_seconds'),
  }
}
