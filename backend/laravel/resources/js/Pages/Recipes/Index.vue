<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Рецепты</h1>
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <label class="text-sm text-neutral-300">Поиск:</label>
      <input v-model="query" placeholder="Название или культура..." class="h-9 w-64 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
      <Link href="/recipes/create" class="ml-auto">
        <Button size="sm">Создать рецепт</Button>
      </Link>
    </div>
    <div v-if="filtered.length === 0" class="text-sm text-neutral-400 px-1 py-6">
      {{ all.length === 0 ? 'Рецепты не найдены' : 'Нет рецептов по текущему фильтру' }}
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      <Card 
        v-for="r in filtered" 
        :key="r.id"
        v-memo="[r.id, r.name, r.description, r.phases_count]"
      >
        <div class="flex items-start justify-between">
          <div>
            <div class="text-sm font-semibold">{{ r.name }}</div>
            <div class="text-xs text-neutral-400">{{ r.description || 'Без описания' }} · Фаз: {{ r.phases_count || 0 }}</div>
          </div>
          <Link :href="`/recipes/${r.id}`" class="text-sky-400 text-sm hover:underline">Открыть</Link>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import type { Recipe } from '@/types'

const page = usePage<{ recipes?: Recipe[] }>()
const all = computed(() => (page.props.recipes || []) as Recipe[])
const query = ref<string>('')

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
</script>

