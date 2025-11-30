<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">Рецепты</h1>
      <Button size="sm" variant="primary" @click="openRecipeWizard">
        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Новый цикл
      </Button>
    </div>
    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Поиск:</label>
        <input v-model="query" placeholder="Название или культура..." class="h-9 flex-1 sm:w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
      </div>
    </div>
    <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
      <!-- Заголовок таблицы -->
      <div class="flex-shrink-0 grid grid-cols-4 gap-0 bg-neutral-900 text-neutral-300 text-sm border-b border-neutral-800">
        <div v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium">
          {{ h }}
        </div>
      </div>
      <!-- Виртуализированный список -->
      <div class="flex-1 overflow-hidden">
        <RecycleScroller
          :items="rows"
          :item-size="rowHeight"
          key-field="0"
          v-slot="{ item: r, index }"
          class="virtual-table-body h-full"
        >
          <div 
            :class="index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925'" 
            class="grid grid-cols-4 gap-0 text-sm border-b border-neutral-900"
            style="height:44px"
          >
            <div class="px-3 py-2 flex items-center">
              <Link :href="`/recipes/${r[0]}`" class="text-sky-400 hover:underline">{{ r[1] }}</Link>
            </div>
            <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[2] || 'Без описания' }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[3] || 0 }}</div>
            <div class="px-3 py-2 flex items-center">
              <Link :href="`/recipes/${r[0]}`">
                <Button size="sm" variant="secondary">Открыть</Button>
              </Link>
            </div>
          </div>
        </RecycleScroller>
        <div v-if="!rows.length" class="text-sm text-neutral-400 px-3 py-6">
          {{ all.length === 0 ? 'Рецепты не найдены' : 'Нет рецептов по текущему фильтру' }}
        </div>
      </div>
    </div>

    <!-- Мастер создания рецепта -->
    <RecipeCreateWizard
      :show="showRecipeWizard"
      @close="closeRecipeWizard"
      @created="onRecipeCreated"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import RecipeCreateWizard from '@/Components/RecipeCreateWizard.vue'
import { useSimpleModal } from '@/composables/useModal'
import type { Recipe } from '@/types'

const headers = ['Название', 'Описание', 'Фаз', 'Действия']
const page = usePage<{ recipes?: Recipe[] }>()
const all = computed(() => (page.props.recipes || []) as Recipe[])
const query = ref<string>('')

const { isOpen: showRecipeWizard, open: openRecipeWizard, close: closeRecipeWizard } = useSimpleModal()

function onRecipeCreated(recipe: Recipe): void {
  // Обновляем страницу для отображения нового рецепта
  router.reload({ only: ['recipes'] })
}

// Оптимизируем фильтрацию: мемоизируем нижний регистр запроса
const queryLower = computed(() => query.value.toLowerCase())
const filtered = computed(() => {
  const q = queryLower.value
  if (!q) {
    return all.value // Если запроса нет, возвращаем все рецепты
  }
  
  return all.value.filter(r => {
    return r.name?.toLowerCase().includes(q) || r.description?.toLowerCase().includes(q)
  })
})

// Преобразуем рецепты в строки таблицы
const rows = computed(() => {
  return filtered.value.map(r => [
    r.id,
    r.name || '-',
    r.description || 'Без описания',
    r.phases_count || 0,
    r.id // Добавляем ID в конец для удобства доступа
  ])
})

// Виртуализация через RecycleScroller
const rowHeight = 44
</script>

