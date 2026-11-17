import { describe, expect, it } from 'vitest'
import { buildRecipePhasePayload, createDefaultRecipePhase, getRecipePhaseTargetValidationError } from '../recipeEditorShared'
import {
  durationDisplay, setDurationFromString, intervalDisplay, setIntervalFromString,
  durationIrrigDisplay, setDurationIrrigFromString, cropDayInputValue, setCropDayNumber,
  onPhTargetChange, onEcTargetChange, onPhNightTargetChange, onEcNightTargetChange,
  ecBreakdownForTarget,
} from '../recipePhaseFields'

describe('recipe phase field edits', () => {
  it('preserves duration and irrigation units through the API payload', () => {
    const phase = createDefaultRecipePhase(0)
    setDurationFromString(phase, '2 : 03')
    setIntervalFromString(phase, '01 : 45')
    setDurationIrrigFromString(phase, '02 : 15')
    expect(durationDisplay(phase)).toBe('2 : 03')
    expect(intervalDisplay(phase)).toBe('01 : 45')
    expect(durationIrrigDisplay(phase)).toBe('02 : 15')
    expect(buildRecipePhasePayload(phase)).toMatchObject({
      duration_hours: 51, irrigation_interval_sec: 6300, irrigation_duration_sec: 135,
    })
  })

  it('rejects malformed time rather than silently changing it; keeps explicit blank behavior', () => {
    const phase = createDefaultRecipePhase(0)
    setDurationFromString(phase, '1:99')
    setIntervalFromString(phase, '-2:99')
    setDurationIrrigFromString(phase, '1:99')
    expect(phase.duration_hours).toBeNaN()
    expect(phase.irrigation_interval_sec).toBeNaN()
    expect(phase.irrigation_duration_sec).toBeNaN()
    expect(getRecipePhaseTargetValidationError(phase)).toContain('проверьте формат времени')
    setDurationFromString(phase, '')
    setIntervalFromString(phase, '')
    setDurationIrrigFromString(phase, '')
    expect(phase.duration_hours).toBe(0)
    expect(phase.irrigation_interval_sec).toBe(0)
    expect(phase.irrigation_duration_sec).toBe(0)
  })

  it('keeps blank crop thresholds nullable rather than enabling a zero threshold', () => {
    const phase = createDefaultRecipePhase(0)
    setCropDayNumber(phase, 'dli_target', { target: { value: ' ' } } as unknown as Event)
    setCropDayNumber(phase, 'solution_temp_min', { target: { value: '0' } } as unknown as Event)
    expect(cropDayInputValue(phase.dli_target)).toBe('')
    expect(buildRecipePhasePayload(phase)).toMatchObject({ dli_target: null, solution_temp_min: 0 })
  })

  it('updates day and night limits independently without floating point tails', () => {
    const phase = createDefaultRecipePhase(0)
    phase.ph_target = 5.8
    phase.ec_target = 1.4
    phase.day_night.ph.night = 6.1
    phase.day_night.ec.night = 1.7
    onPhTargetChange(phase)
    onEcTargetChange(phase)
    onPhNightTargetChange(phase)
    onEcNightTargetChange(phase)
    expect([phase.ph_min, phase.ph_max, phase.ec_min, phase.ec_max]).toEqual([5.7, 5.9, 1.3, 1.5])
    expect([phase.day_night.ph.night_min, phase.day_night.ph.night_max]).toEqual([6, 6.2])
    expect([phase.day_night.ec.night_min, phase.day_night.ec.night_max]).toEqual([1.6, 1.8])
  })

  it('computes a night EC preview without mutating the day target', () => {
    const phase = createDefaultRecipePhase(0)
    const before = structuredClone(phase)
    ecBreakdownForTarget(phase, 6, 2)
    expect(phase).toEqual(before)
  })
})
