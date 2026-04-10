<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <h1 class="text-lg font-semibold">
          {{ recipe?.id ? 'Редактировать рецепт' : 'Создать рецепт' }}
        </h1>
        <div class="flex items-center gap-2">
          <Link
            v-if="recipe?.id"
            :href="`/recipes/${recipe.id}`"
          >
            <Button
              size="sm"
              variant="secondary"
            >
              К рецепту
            </Button>
          </Link>
          <Button
            size="sm"
            :disabled="processing"
            data-testid="save-recipe-button"
            @click="onSave"
          >
            {{ processing ? 'Сохранение...' : 'Сохранить' }}
          </Button>
        </div>
      </div>

      <Card>
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
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import RecipeEditor from '@/Components/RecipeEditor.vue'
import { useRecipeEditor } from '@/composables/useRecipeEditor'
import type { Recipe } from '@/types'

const page = usePage<{ recipe?: Recipe }>()
const recipe = page.props.recipe ?? null

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
  addPhase,
  removePhase,
  saveRecipe,
} = useRecipeEditor(recipe)

onMounted(() => {
  void loadPlants()
  void loadNutrientProducts()
})

function onSave(): void {
  void saveRecipe({ redirectToRecipe: Boolean(recipe?.id) })
}
</script>
