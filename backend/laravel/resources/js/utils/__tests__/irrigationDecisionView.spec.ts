import { describe, expect, it } from 'vitest'
import { irrigationDecisionFacts, irrigationOutcomeLabel, irrigationReasonPresentation } from '../irrigationDecisionView'
import { resolveRecipePhasePidTargets } from '@/composables/recipePhasePidTargets'

describe('irrigation decision evidence', () => {
  it('describes approval as permission rather than confirmed watering', () => {
    expect(irrigationOutcomeLabel('run')).toBe('Полив разрешён')
    expect(irrigationOutcomeLabel(null)).toBe('Решение ещё не принято')
    expect(irrigationOutcomeLabel('unexpected')).toBe('Результат решения неизвестен')
  })

  it('retains the agronomic meaning of degraded reasons', () => {
    expect(irrigationReasonPresentation('smart_soil_degraded_below_min'))
      .toEqual(irrigationReasonPresentation('smart_soil_below_min'))
    expect(irrigationReasonPresentation('smart_soil_telemetry_missing_or_stale').action).toContain('всех активных датчиков')
  })

  it('never turns missing or invalid evidence into zero', () => {
    const facts = irrigationDecisionFacts({ details: { zone_average_pct: null, samples: false, spread_pct: Number.NaN } })
    expect(facts).toEqual([])
    expect(irrigationDecisionFacts({ details: { zone_average_pct: 0 } })[0].value).toBe('0%')
  })

  it.each([null, undefined, '', ' ', false, true])('keeps absent recipe targets empty: %s', value => {
    const result = resolveRecipePhasePidTargets({ ph_target: value, ec_target: value })
    expect(result?.ph).toBeNull()
    expect(result?.ec).toBeNull()
  })
})
