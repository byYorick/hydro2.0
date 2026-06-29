import { describe, expect, it } from 'vitest'
import { parsePrometheusScalar, parseSchedulerDispatchMetrics } from '@/utils/prometheusText'

describe('prometheusText', () => {
  it('парсит scalar gauge без labels', () => {
    const text = [
      '# HELP laravel_scheduler_pending_intents_count test',
      'laravel_scheduler_pending_intents_count 7',
    ].join('\n')

    expect(parsePrometheusScalar(text, 'laravel_scheduler_pending_intents_count')).toBe(7)
  })

  it('парсит ключевые метрики scheduler dispatch', () => {
    const text = [
      'laravel_scheduler_pending_intents_count 2',
      'laravel_scheduler_oldest_pending_intent_age_seconds 45.5',
      'laravel_scheduler_dispatch_cycle_overrun_seconds 0',
    ].join('\n')

    expect(parseSchedulerDispatchMetrics(text)).toEqual({
      pendingIntents: 2,
      oldestPendingAgeSec: 45.5,
      dispatchCycleOverrunSec: 0,
    })
  })
})
