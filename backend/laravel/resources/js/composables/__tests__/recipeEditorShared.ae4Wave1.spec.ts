import { describe, expect, it } from 'vitest'
import {
  buildRecipePhasePayload,
  createDefaultRecipePhase,
  hydrateRecipePhaseForm,
} from '@/composables/recipeEditorShared'

describe('recipeEditorShared ae4 wave1 fields', () => {
  it('принимает soil_moisture/vpd/light_integral в hydrate и payload', () => {
    const hydrated = hydrateRecipePhaseForm({
      phase_index: 0,
      name: 'Вега',
      duration_hours: 72,
      soil_moisture_min: 35,
      soil_moisture_max: 55,
      vpd_min: 0.8,
      vpd_max: 1.4,
      light_integral_per_shot: 12000,
    })
    expect(hydrated.soil_moisture_min).toBe(35)
    expect(hydrated.vpd_max).toBe(1.4)
    expect(hydrated.light_integral_per_shot).toBe(12000)

    const payload = buildRecipePhasePayload(hydrated)
    expect(payload.soil_moisture_min).toBe(35)
    expect(payload.vpd_min).toBe(0.8)
    expect(payload.light_integral_per_shot).toBe(12000)
    expect(payload.extensions).not.toHaveProperty('vpd_min')
  })

  it('дефолт фазы не создаёт отдельное меню и оставляет новые поля пустыми', () => {
    const phase = createDefaultRecipePhase(0)
    expect(phase.soil_moisture_min).toBeNull()
    expect(phase.vpd_min).toBeNull()
    expect(phase.light_integral_per_shot).toBeNull()
  })
})
