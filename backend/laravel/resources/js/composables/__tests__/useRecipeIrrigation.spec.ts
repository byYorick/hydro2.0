import { afterEach, describe, expect, it } from 'vitest'
import { effectScope, nextTick, ref, type EffectScope } from 'vue'
import type { Substrate } from '@/services/api/substrates'
import { createDefaultRecipePhase, createRecipeEditorFormState } from '../recipeEditorShared'
import { useRecipeIrrigation } from '../useRecipeIrrigation'

const substrates: Substrate[] = [
  { id: 1, code: 'soil', name: 'Soil', components: [], applicable_systems: ['drip_tape'] },
  { id: 2, code: 'rockwool', name: 'Rockwool', components: [], applicable_systems: ['drip_emitter'] },
  { id: 3, code: 'water', name: 'Water', components: [], applicable_systems: ['nft', 'dwc', 'aeroponics'] },
  { id: 4, code: 'hydroton', name: 'Hydroton', components: [], applicable_systems: ['ebb_flow'] },
]
const scopes: EffectScope[] = []
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()) })
function editor() {
  const form = ref(createRecipeEditorFormState())
  form.value.phases.push(createDefaultRecipePhase(1))
  const scope = effectScope()
  scopes.push(scope)
  return { form, irrigation: scope.run(() => useRecipeIrrigation(form, () => substrates))! }
}

describe('recipe-wide irrigation state', () => {
  it('changes every phase and selects compatible substrates after the reactive update', async () => {
    const { form, irrigation } = editor()
    irrigation.recipeIrrigationMode.value = 'RECIRC'
    await nextTick()
    expect(form.value.phases.map(p => [p.irrigation_mode, p.irrigation_system_type, p.substrate_type]))
      .toEqual([['RECIRC', 'nft', 'water'], ['RECIRC', 'nft', 'water']])
    irrigation.recipeIrrigationMode.value = 'SUBSTRATE'
    await nextTick()
    expect(form.value.phases.map(p => [p.irrigation_system_type, p.substrate_type]))
      .toEqual([['drip_tape', 'soil'], ['drip_tape', 'soil']])
  })

  it('preserves an already compatible system when selecting the same mode', async () => {
    const { form, irrigation } = editor()
    form.value.phases[1].irrigation_system_type = 'drip_emitter'
    await nextTick()
    irrigation.recipeIrrigationMode.value = 'SUBSTRATE'
    await nextTick()
    expect(form.value.phases[1].irrigation_system_type).toBe('drip_emitter')
    expect(form.value.phases[1].substrate_type).toBe('rockwool')
  })

  it('uses a compatible fallback when a system has no default substrate in the catalog', async () => {
    const { form, irrigation } = editor()
    form.value.phases[0].irrigation_system_type = 'dwc'
    await nextTick()
    expect(irrigation.substrateOptions(form.value.phases[0])).toEqual([{ value: 'water', label: 'Water' }])
    form.value.phases[0].irrigation_system_type = 'drip'
    await nextTick()
    expect(form.value.phases[0].substrate_type).toBeNull()
  })

  it('applies a newly created compatible substrate to matching phases', async () => {
    const { form, irrigation } = editor()
    await nextTick()
    irrigation.applyCreatedSubstrate({ id: 5, code: 'custom', name: 'Custom', components: [], applicable_systems: [] })
    expect(form.value.phases.map(p => p.substrate_type)).toEqual(['custom', 'custom'])
    irrigation.applyCreatedSubstrate(substrates[2])
    expect(form.value.phases.map(p => p.substrate_type)).toEqual(['custom', 'custom'])
  })

  it('follows a replacement model and newly added phases without retaining the old form', async () => {
    const { form, irrigation } = editor()
    const replacement = createRecipeEditorFormState()
    replacement.phases[0].irrigation_mode = 'RECIRC'
    replacement.phases[0].irrigation_system_type = 'dwc'
    form.value = replacement
    await nextTick()
    expect(irrigation.recipeIrrigationMode.value).toBe('RECIRC')
    expect(form.value.phases[0].substrate_type).toBe('water')
    const phase = createDefaultRecipePhase(1)
    phase.irrigation_system_type = 'drip_emitter'
    form.value.phases.push(phase)
    await nextTick()
    expect(form.value.phases[1].substrate_type).toBe('rockwool')
  })
})
