import { computed, ref, watch, type Ref } from 'vue'
import type { PlantOption, RecipeEditorFormState } from './recipeEditorShared'

export function useRecipeIdentity(form: Ref<RecipeEditorFormState>, plants: () => PlantOption[]) {
  const recipeLabel = ref(form.value.description || '')

  const selectedPlantName = computed(() => {
    const plant = plants().find(p => p.id === form.value.plant_id)
    return plant?.name ?? ''
  })

  const recipeName = computed(() => {
    const plant = selectedPlantName.value
    const label = recipeLabel.value.trim()
    if (plant && label) return `${plant} ${label}`
    if (plant) return plant
    return label || ''
  })

  watch(recipeName, (name) => { form.value.name = name }, { immediate: true })
  watch(recipeLabel, (label) => { form.value.description = label })

  return { recipeLabel, recipeName }
}
