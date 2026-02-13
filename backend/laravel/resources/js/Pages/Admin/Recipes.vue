<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">
      Admin · Recipes
    </h1>
    <Card class="mb-4">
      <div class="text-sm font-semibold mb-2">
        Quick Update Recipe
      </div>
      <form
        class="grid grid-cols-1 md:grid-cols-3 gap-2"
        @submit.prevent="onUpdate"
      >
        <select
          v-model="selectedId"
          class="input-select"
        >
          <option
            v-for="r in recipes"
            :key="r.id"
            :value="r.id"
          >
            {{ r.name }}
          </option>
        </select>
        <input
          v-model="form.name"
          placeholder="New name"
          class="input-field"
        />
        <input
          v-model="form.description"
          placeholder="Description"
          class="input-field"
        />
        <div class="md:col-span-3">
          <Button
            size="sm"
            type="submit"
          >
            Update
          </Button>
        </div>
      </form>
    </Card>
    <Card>
      <div class="text-sm font-semibold mb-2">
        Recipes
      </div>
      <ul class="text-sm text-[color:var(--text-muted)] space-y-1">
        <li
          v-for="r in recipes"
          :key="r.id"
        >
          {{ r.name }} — {{ r.description || 'Без описания' }} — phases: {{ r.phases_count }}
        </li>
      </ul>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { reactive, ref, computed } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useRecipesStore } from '@/stores/recipes'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import type { Recipe } from '@/types/Recipe'

interface PageProps {
  recipes?: Recipe[]
  [key: string]: any
}

const page = usePage<PageProps>()
const { showToast } = useToast()
const { api } = useApi(showToast)
const recipesStore = useRecipesStore()

// Инициализируем store из props
if (page.props.recipes) {
  recipesStore.initFromProps({ recipes: page.props.recipes })
}

const recipes = computed(() => recipesStore.allRecipes)
const selectedId = ref<number | null>(recipes.value[0]?.id || null)
const form = reactive<{ name: string; description: string }>({ 
  name: '', 
  description: '' 
})

async function onUpdate(): Promise<void> {
  if (!selectedId.value) return
  
  try {
    const response = await api.patch<{ data?: Recipe } | Recipe>(`/recipes/${selectedId.value}`, form)
    const updatedRecipe = extractData<Recipe>(response.data) || response.data as Recipe
    
    // Обновляем рецепт в store вместо reload
    if (updatedRecipe?.id) {
      recipesStore.upsert(updatedRecipe)
      logger.debug('[Admin/Recipes] Recipe updated in store', { recipeId: updatedRecipe.id })
    }
    
    form.name = ''
    form.description = ''
    showToast('Recipe updated successfully', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('[Admin/Recipes] Failed to update recipe:', err)
    if (!(err as any)?.response) {
      showToast(`Не удалось обновить рецепт: ${extractHumanErrorMessage(err, 'Ошибка обновления')}`, 'error', TOAST_TIMEOUT.NORMAL)
    }
  }
}
</script>
