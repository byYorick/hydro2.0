<template>
  <AppLayout>
    <section class="ui-hero p-5 space-y-4 mb-4">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            агрономия
          </p>
          <h1 class="text-2xl font-semibold tracking-tight mt-1 text-[color:var(--text-primary)]">
            Рецепты
          </h1>
          <p class="text-sm text-[color:var(--text-muted)]">
            Управление рецептами выращивания и фазами для автоматических циклов.
          </p>
          <div class="mt-2 flex items-center gap-3 text-sm">
            <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
              Справочники
            </span>
            <Link
              href="/plants"
              class="text-[color:var(--accent-cyan)] hover:underline"
            >
              Культуры
            </Link>
            <Link
              href="/nutrients"
              class="text-[color:var(--accent-cyan)] hover:underline"
            >
              Удобрения
            </Link>
          </div>
        </div>
        <Link
          v-if="canEditRecipes"
          href="/recipes/create"
        >
          <Button
            size="sm"
            variant="primary"
          >
            <svg
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 4v16m8-8H4"
              />
            </svg>
            Новый рецепт
          </Button>
        </Link>
      </div>
    </section>
    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-[color:var(--text-muted)] shrink-0">Поиск:</label>
        <input
          v-model="query"
          placeholder="Название или культура..."
          class="input-field flex-1 sm:w-56"
        />
      </div>
    </div>
    <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[720px] flex flex-col">
      <div class="overflow-auto flex-1">
        <table class="w-full border-collapse">
          <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] text-sm sticky top-0 z-10">
            <tr>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Название
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Культура
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Версия
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Зон в работе
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Фаз
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Длительность
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Структура фаз
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Действия
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in rows"
              :key="row.id"
              :class="index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]'"
              class="text-sm border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)] transition-colors"
            >
              <td class="px-3 py-2">
                <Link
                  :href="`/recipes/${row.id}`"
                  class="text-[color:var(--accent-cyan)] hover:underline truncate block"
                >
                  {{ row.name }}
                </Link>
                <span class="block text-xs text-[color:var(--text-muted)] truncate">{{ row.description }}</span>
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ row.crop }}
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ row.versionLabel }}
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ row.zonesLabel }}
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ row.phasesCount }}
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ row.durationLabel }}
              </td>
              <td class="px-3 py-2">
                <RecipeMiniTimeline :phases="row.phasesPreview" />
              </td>
              <td class="px-3 py-2">
                <Link :href="`/recipes/${row.id}`">
                  <Button
                    size="sm"
                    variant="secondary"
                  >
                    Открыть
                  </Button>
                </Link>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td
                colspan="8"
                class="px-3 py-6 text-sm text-[color:var(--text-dim)] text-center"
              >
                {{ all.length === 0 ? 'Рецепты не найдены' : 'Нет рецептов по текущему фильтру' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pagination
        v-model:current-page="currentPage"
        v-model:per-page="perPage"
        :total="filtered.length"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Pagination from '@/Components/Pagination.vue'
import RecipeMiniTimeline from '@/Components/Recipes/RecipeMiniTimeline.vue'
import { useRole } from '@/composables/useRole'
import { formatDurationHours } from '@/utils/recipeVisualization'
import type { Recipe } from '@/types'

const page = usePage<{ recipes?: Recipe[] }>()
const all = computed(() => (page.props.recipes || []) as Recipe[])
const { canEditRecipes } = useRole()
const query = ref<string>('')
const currentPage = ref<number>(1)
const perPage = ref<number>(25)

function cropLabel(recipe: Recipe): string {
  const names = (recipe.plants ?? []).map((plant) => plant.name).filter(Boolean)
  return names.length > 0 ? names.join(', ') : '—'
}

function versionLabel(recipe: Recipe): string {
  return recipe.latest_published_revision_id ? 'опубликован' : 'черновик'
}

function zonesLabel(recipe: Recipe): string {
  return typeof recipe.active_zones_count === 'number' ? String(recipe.active_zones_count) : '—'
}

const queryLower = computed(() => query.value.toLowerCase())
const filtered = computed(() => {
  const q = queryLower.value
  if (!q) {
    return all.value
  }

  return all.value.filter((recipe) => {
    return recipe.name?.toLowerCase().includes(q)
      || recipe.description?.toLowerCase().includes(q)
      || cropLabel(recipe).toLowerCase().includes(q)
  })
})

function clampCurrentPage(total: number): number {
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  return validPage
}

watch([filtered, perPage], () => {
  if (filtered.value.length > 0) {
    clampCurrentPage(filtered.value.length)
  } else {
    currentPage.value = 1
  }
})

const paginatedRecipes = computed(() => {
  const total = filtered.value.length
  if (total === 0) return []

  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filtered.value.slice(start, end)
})

const rows = computed(() => {
  return paginatedRecipes.value.map((recipe) => ({
    id: recipe.id,
    name: recipe.name || '-',
    description: recipe.description || 'Без описания',
    crop: cropLabel(recipe),
    versionLabel: versionLabel(recipe),
    zonesLabel: zonesLabel(recipe),
    phasesCount: recipe.phases_count || 0,
    durationLabel: formatDurationHours(recipe.total_duration_hours ?? null),
    phasesPreview: recipe.phases_preview ?? [],
  }))
})

watch(query, () => {
  currentPage.value = 1
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
  min-width: 140px;
  max-width: 240px;
}

th:nth-child(5),
td:nth-child(5) {
  min-width: 80px;
  text-align: center;
}

th:nth-child(7),
td:nth-child(7) {
  min-width: 120px;
}

th:last-child,
td:last-child {
  min-width: 120px;
  text-align: center;
}
</style>
