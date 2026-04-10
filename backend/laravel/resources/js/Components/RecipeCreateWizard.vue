<template>
  <Modal
    :open="show"
    title="Создать новый рецепт"
    size="large"
    @close="$emit('close')"
  >
    <RecipeEditor
      v-model:form="form"
      :plants="plants"
      :plants-loading="plantsLoading"
      :npk-products="npkProducts"
      :calcium-products="calciumProducts"
      :magnesium-products="magnesiumProducts"
      :micro-products="microProducts"
      @add-phase="addPhase"
      @remove-phase="removePhase"
    />

    <template #footer>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('close')"
      >
        Отмена
      </Button>
      <Button
        size="sm"
        :disabled="processing"
        @click="onCreate"
      >
        {{ processing ? 'Создание...' : 'Создать рецепт' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import Modal from './Modal.vue'
import Button from './Button.vue'
import RecipeEditor from './RecipeEditor.vue'
import { useRecipeEditor } from '@/composables/useRecipeEditor'
import type { Recipe } from '@/types'

interface Props {
  show: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [recipe: Recipe]
}>()

const {
  form,
  processing,
  plants,
  plantsLoading,
  npkProducts,
  calciumProducts,
  magnesiumProducts,
  microProducts,
  loadPlants,
  loadNutrientProducts,
  reset,
  addPhase,
  removePhase,
  saveRecipe,
} = useRecipeEditor()

watch(
  () => props.show,
  (show) => {
    if (show) {
      reset(null)
      void loadPlants()
      void loadNutrientProducts()
    }
  },
  { immediate: true }
)

onMounted(() => {
  void loadPlants()
  void loadNutrientProducts()
})

async function onCreate(): Promise<void> {
  const recipe = await saveRecipe({ redirectToRecipe: false })
  if (!recipe) {
    return
  }

  emit('created', recipe)
  emit('close')
}
</script>
