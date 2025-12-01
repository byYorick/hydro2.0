<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Admin · Recipes</h1>
    <Card class="mb-4">
      <div class="text-sm font-semibold mb-2">Quick Update Recipe</div>
      <form class="grid grid-cols-1 md:grid-cols-3 gap-2" @submit.prevent="onUpdate">
        <select v-model="selectedId" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option v-for="r in recipes" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
        <input v-model="form.name" placeholder="New name" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
        <input v-model="form.description" placeholder="Description" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
        <div class="md:col-span-3">
          <Button size="sm" type="submit">Update</Button>
        </div>
      </form>
    </Card>
    <Card>
      <div class="text-sm font-semibold mb-2">Recipes</div>
      <ul class="text-sm text-neutral-300 space-y-1">
        <li v-for="r in recipes" :key="r.id">{{ r.name }} — {{ r.description || 'Без описания' }} — phases: {{ r.phases_count }}</li>
      </ul>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { reactive, ref, computed } from 'vue'
import { usePage, router } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useRecipesStore } from '@/stores/recipes'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import type { Recipe } from '@/types/Recipe'

interface PageProps {
  recipes?: Recipe[]
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
const selectedId = ref<number | null>(recipes[0]?.id || null)
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
    // Ошибка уже обработана в useApi через showToast
  }
}
</script>

