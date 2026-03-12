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
      <div class="overflow-auto flex-1">
        <table class="w-full border-collapse">
          <thead class="bg-neutral-900 text-neutral-300 text-sm sticky top-0 z-10">
            <tr>
              <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Название</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Описание</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Фаз</th>
              <th class="text-left px-3 py-2 font-semibold border-b border-neutral-800">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(r, index) in rows"
              :key="r[0]"
              :class="index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925'"
              class="text-sm border-b border-neutral-900 hover:bg-neutral-900 transition-colors"
            >
              <td class="px-3 py-2">
                <Link :href="`/recipes/${r[0]}`" class="text-sky-400 hover:underline truncate block">{{ r[1] }}</Link>
              </td>
              <td class="px-3 py-2 text-xs text-neutral-400">
                <span class="truncate block">{{ r[2] || 'Без описания' }}</span>
              </td>
              <td class="px-3 py-2 text-xs text-neutral-400">{{ r[3] || 0 }}</td>
              <td class="px-3 py-2">
                <Link :href="`/recipes/${r[0]}`">
                  <Button size="sm" variant="secondary">Открыть</Button>
                </Link>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="4" class="px-3 py-6 text-sm text-neutral-400 text-center">
                {{ all.length === 0 ? 'Рецепты не найдены' : 'Нет рецептов по текущему фильтру' }}
              </td>
            </tr>
          </tbody>
        </table>
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

</script>

<style scoped>
table {
  table-layout: auto;
}

th, td {
  white-space: nowrap;
}

th:first-child,
td:first-child {
  white-space: normal;
  min-width: 200px;
  max-width: 300px;
}

th:nth-child(2),
td:nth-child(2) {
  white-space: normal;
  min-width: 250px;
  max-width: 400px;
}

th:nth-child(3),
td:nth-child(3) {
  min-width: 80px;
  text-align: center;
}

th:last-child,
td:last-child {
  min-width: 120px;
  text-align: center;
}
</style>

