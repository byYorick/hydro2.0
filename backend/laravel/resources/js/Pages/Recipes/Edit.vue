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

      <div
        v-if="activeUsage && activeUsage.count > 0"
        class="rounded-md border border-amber-400/60 bg-amber-50 dark:bg-amber-900/20 p-3 text-sm text-amber-900 dark:text-amber-100"
        data-testid="recipe-active-usage-warning"
      >
        <div class="font-semibold mb-1">
          ⚠ Рецепт активен в {{ activeUsage.count }} зон(е/ах)
        </div>
        <div class="text-xs leading-relaxed">
          Сохранение создаст <b>новую DRAFT-ревизию</b> и опубликует её. Активные циклы продолжат работать
          на <b>текущей PUBLISHED-версии</b> до явного переключения через «Сменить ревизию» в зоне.
        </div>
        <ul class="mt-1.5 text-xs space-y-0.5">
          <li
            v-for="item in activeUsage.active_cycles"
            :key="item.cycle_id"
          >
            • Зона <b>{{ item.zone_name || `#${item.zone_id}` }}</b> — ревизия v{{ item.revision_number }} ({{ item.status }})
          </li>
        </ul>
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
          :substrates="substrates"
          @add-phase="addPhase"
          @remove-phase="removePhase"
          @plant-created="onPlantCreated"
          @product-created="onProductCreated"
          @substrate-created="onSubstrateCreated"
          @save="onSave"
        />
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import RecipeEditor from '@/Components/RecipeEditor.vue'
import { useRecipeEditor } from '@/composables/useRecipeEditor'
import { api } from '@/services/api'
import type { RecipeActiveUsage } from '@/services/api/recipes'
import type { Recipe, NutrientProduct } from '@/types'
import type { Substrate } from '@/services/api/substrates'

const page = usePage<{ recipe?: Recipe }>()
const recipe = page.props.recipe ?? null

const {
  form,
  processing,
  plants,
  plantsLoading,
  nutrientProducts,
  npkProducts,
  calciumProducts,
  magnesiumProducts,
  microProducts,
  substrates,
  loadPlants,
  loadNutrientProducts,
  loadSubstrates,
  addPhase,
  removePhase,
  saveRecipe,
} = useRecipeEditor(recipe)

const activeUsage = ref<RecipeActiveUsage | null>(null)

async function loadActiveUsage(): Promise<void> {
  if (!recipe?.id) return
  try {
    activeUsage.value = await api.recipes.getActiveUsage(recipe.id)
  } catch {
    activeUsage.value = null
  }
}

onMounted(() => {
  void loadPlants()
  void loadNutrientProducts()
  void loadSubstrates()
  void loadActiveUsage()
})

function onPlantCreated(plant: { id: number; name: string }): void {
  if (!plants.value.some(p => p.id === plant.id)) {
    plants.value.push(plant)
  }
}

function onProductCreated(product: NutrientProduct): void {
  if (!nutrientProducts.value.some(p => p.id === product.id)) {
    nutrientProducts.value.push(product)
  }
}

function onSubstrateCreated(substrate: Substrate): void {
  if (!substrates.value.some(s => s.id === substrate.id)) {
    substrates.value.push(substrate)
  }
}

function onSave(): void {
  void saveRecipe({ redirectToRecipe: Boolean(recipe?.id) })
}
</script>
