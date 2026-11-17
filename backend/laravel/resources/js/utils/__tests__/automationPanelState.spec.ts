import { describe, expect, it } from 'vitest'
import { normalizeAutomationPanelState } from '../automationPanelState'
import { processStageLabel } from '../automationProcessLabels'

describe('automation state presentation boundaries', () => {
  it('does not present compatibility placeholders as real empty tanks', () => {
    const state = normalizeAutomationPanelState({ state: 'IDLE', compatibility: { source: 'ae3_control_mode_fallback' }, current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: 0 } }, { zoneId: 7 })
    expect(state.current_levels.clean_tank_level_percent).toBeNull()
    expect(state.current_levels.nutrient_tank_level_percent).toBeNull()
    expect(state.compatibility?.source).toBe('ae3_control_mode_fallback')
  })
  it('retains observed zero levels from the normal state endpoint', () => {
    const state = normalizeAutomationPanelState({ state: 'IDLE', current_levels: { clean_tank_level_percent: 0 } }, { zoneId: 7 })
    expect(state.current_levels.clean_tank_level_percent).toBe(0)
  })
  it('translates known stages and marks an unsupported stage explicitly', () => {
    expect(processStageLabel('irrigation_run')).toBe('Выполнение полива')
    expect(processStageLabel('corr_check')).toBe('Проверка условий коррекции')
    expect(processStageLabel('future_stage')).toBe('Этап не распознан')
  })
})
