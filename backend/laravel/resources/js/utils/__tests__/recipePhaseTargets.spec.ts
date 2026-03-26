import { describe, expect, it } from 'vitest'
import { resolveCurrentRecipePhase, resolveRecipePhaseTargets } from '../recipePhaseTargets'

describe('resolveRecipePhaseTargets', () => {
  it('returns nested targets as-is when phase already has normalized targets', () => {
    const targets = {
      ph: { target: 5.8, min: 5.6, max: 6.0 },
      ec: { target: 1.6, min: 1.4, max: 1.8 },
    }

    expect(resolveRecipePhaseTargets({ targets })).toEqual(targets)
  })

  it('builds normalized targets from flat recipe phase fields', () => {
    expect(
      resolveRecipePhaseTargets({
        ph_target: '5.80',
        ph_min: '5.60',
        ph_max: '6.00',
        ec_target: 1.6,
        ec_min: 1.4,
        ec_max: 1.8,
        temp_air_target: 24,
        humidity_target: 60,
        irrigation_mode: 'SUBSTRATE',
        irrigation_interval_sec: 1800,
        irrigation_duration_sec: 90,
      })
    ).toEqual({
      ph: { target: 5.8, min: 5.6, max: 6 },
      ec: { target: 1.6, min: 1.4, max: 1.8 },
      temp_air: 24,
      humidity_air: 60,
      climate_request: {
        temp_air_target: 24,
        humidity_target: 60,
      },
      irrigation_interval_sec: 1800,
      irrigation_duration_sec: 90,
      irrigation: {
        mode: 'SUBSTRATE',
        interval_sec: 1800,
        duration_sec: 90,
      },
    })
  })

  it('returns null when phase has no target data', () => {
    expect(resolveRecipePhaseTargets({ id: 1, name: 'Empty phase' })).toBeNull()
    expect(resolveRecipePhaseTargets(null)).toBeNull()
  })

  it('resolves current recipe phase from recipe revision phases', () => {
    expect(resolveCurrentRecipePhase({
      currentPhase: {
        id: 100,
        phase_index: 0,
        recipe_revision_phase_id: 10,
        ph_target: 5.8,
      },
      recipeRevision: {
        phases: [
          { id: 10, phase_index: 0, ph_target: 5.0, ph_min: 4.9, ph_max: 5.1 },
          { id: 11, phase_index: 1, ph_target: 5.5, ph_min: 5.4, ph_max: 5.6 },
        ],
      },
    })).toEqual({ id: 10, phase_index: 0, ph_target: 5.0, ph_min: 4.9, ph_max: 5.1 })
  })
})
