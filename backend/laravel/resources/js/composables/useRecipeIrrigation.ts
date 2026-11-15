import { computed, watch, type Ref } from 'vue'
import type { RecipeEditorFormState, RecipePhaseFormState } from './recipeEditorShared'
import type { Substrate } from '@/services/api/substrates'

// Дефолтный субстрат для каждого типа полива.
const DEFAULT_SUBSTRATE_FOR: Record<string, string | null> = {
  drip_tape: 'soil',         // капельная лента → грунт
  drip_emitter: 'rockwool',  // капельные форсунки → минеральная вата
  ebb_flow: 'hydroton',      // прилив-отлив → керамзит
  nft: 'water',
  dwc: 'water',
  aeroponics: 'water',
}

export interface SubstrateOption {
  value: string | null
  label: string
}

/** Owns the recipe-wide irrigation mode and phase substrate compatibility. */
export function useRecipeIrrigation(form: Ref<RecipeEditorFormState>, substrates: () => Substrate[]) {
  function substrateOptions(phase: RecipePhaseFormState): SubstrateOption[] {
    const sys = phase.irrigation_system_type
    // Фильтр по совместимости с типом полива
    const compatible = substrates().filter(s => !s.applicable_systems?.length || s.applicable_systems.includes(sys))
    return compatible.map(s => ({ value: s.code, label: s.name }))
  }

  function applyCreatedSubstrate(substrate: Substrate): void {
    // Если в текущей фазе совместим — выбрать его
    const currentPhaseSys = form.value.phases[0]?.irrigation_system_type
    if (!substrate.applicable_systems?.length || substrate.applicable_systems.includes(currentPhaseSys)) {
      form.value.phases.forEach((phase) => {
        if (!substrate.applicable_systems?.length || substrate.applicable_systems.includes(phase.irrigation_system_type)) {
          phase.substrate_type = substrate.code
        }
      })
    }
  }

  // При смене типа полива фазы — если текущий субстрат не совместим, переставить на дефолтный для этого типа.
  watch(
    () => form.value.phases.map(p => p.irrigation_system_type),
    (newTypes, oldTypes) => {
      form.value.phases.forEach((phase, idx) => {
        const opts = substrateOptions(phase)
        const valid = opts.some(o => o.value === phase.substrate_type)
        const typeChanged = oldTypes && newTypes[idx] !== oldTypes[idx]
        if (!valid || typeChanged) {
          const defaultValue = DEFAULT_SUBSTRATE_FOR[phase.irrigation_system_type]
          const defaultIsValid = opts.some(o => o.value === defaultValue)
          phase.substrate_type = defaultIsValid ? defaultValue : (opts[0]?.value ?? null)
        }
      })
    },
    { deep: true, immediate: true },
  )

  // Система подготовки раствора и полива — единая для всех фаз рецепта.
  // Читаем из первой фазы, при изменении обновляем во всех фазах.
  const SUBSTRATE_SYSTEM_TYPES = ['drip_tape', 'drip_emitter'] as const
  const RECIRC_SYSTEM_TYPES = ['nft', 'dwc', 'ebb_flow', 'aeroponics'] as const

  function validSystemTypesFor(mode: 'SUBSTRATE' | 'RECIRC'): readonly string[] {
    return mode === 'SUBSTRATE' ? SUBSTRATE_SYSTEM_TYPES : RECIRC_SYSTEM_TYPES
  }

  const recipeIrrigationMode = computed<'SUBSTRATE' | 'RECIRC'>({
    get: () => form.value.phases[0]?.irrigation_mode ?? 'SUBSTRATE',
    set: (value) => {
      const valid = validSystemTypesFor(value)
      const defaultSystem = valid[0] as RecipePhaseFormState['irrigation_system_type']
      form.value.phases.forEach((phase) => {
        phase.irrigation_mode = value
        if (!valid.includes(phase.irrigation_system_type)) {
          phase.irrigation_system_type = defaultSystem
        }
      })
    },
  })

  return { recipeIrrigationMode, substrateOptions, applyCreatedSubstrate }
}
