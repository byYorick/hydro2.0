<template>
  <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-[color:var(--bg-surface-strong)] text-[color:var(--text-muted)]">
        <tr>
          <th
            v-for="(h, i) in headers"
            :key="i"
            class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]"
          >
            {{ h }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, ri) in paginatedRows"
          :key="ri"
          class="odd:bg-[color:var(--bg-surface-strong)] even:bg-[color:var(--bg-surface)]"
        >
          <td
            v-for="(cell, ci) in row"
            :key="ci"
            class="px-3 py-2 border-b border-[color:var(--border-muted)]"
          >
            <slot
              :name="`cell-${ci}`"
              :value="cell"
            >
              {{ cell }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
    <Pagination
      v-if="rows.length > perPage"
      v-model:current-page="currentPage"
      v-model:per-page="perPage"
      :total="rows.length"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import Pagination from './Pagination.vue'

const props = defineProps({
  headers: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
})

const currentPage = ref<number>(1)
const perPage = ref<number>(25)

const paginatedRows = computed(() => {
  const total = props.rows.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return props.rows.slice(start, end)
})
</script>
