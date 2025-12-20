<template>
  <div v-if="totalPages > 1" class="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
    <div class="text-xs text-[color:var(--text-dim)] order-3 sm:order-1">
      Показано {{ startItem }}-{{ endItem }} из {{ total }}
    </div>
    <div class="flex items-center gap-2 order-1 sm:order-2">
      <button
        @click="goToPage(currentPageModel - 1)"
        :disabled="currentPageModel === 1"
        :aria-label="'Перейти на предыдущую страницу'"
        class="px-3 py-1.5 text-sm rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
        :class="currentPageModel === 1
          ? 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-dim)]'
          : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'"
      >
        <span class="sr-only">Назад</span>
        <span aria-hidden="true">‹</span>
      </button>
      
      <div class="flex items-center gap-1">
        <!-- Первая страница -->
        <button
          v-if="showFirstPage"
          @click="goToPage(1)"
          :aria-label="`Перейти на страницу 1`"
          :aria-current="currentPageModel === 1 ? 'page' : undefined"
          class="min-w-[32px] px-2 py-1.5 text-sm rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
          :class="currentPageModel === 1
            ? 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'"
        >
          1
        </button>
        <span v-if="showFirstEllipsis" class="px-2 text-[color:var(--text-dim)]">...</span>
        
        <!-- Видимые страницы -->
        <button
          v-for="page in visiblePages"
          :key="page"
          @click="goToPage(page)"
          :aria-label="`Перейти на страницу ${page}`"
          :aria-current="page === currentPageModel ? 'page' : undefined"
          class="min-w-[32px] px-2 py-1.5 text-sm rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
          :class="page === currentPageModel
            ? 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'"
        >
          {{ page }}
        </button>
        
        <span v-if="showLastEllipsis" class="px-2 text-[color:var(--text-dim)]">...</span>
        <!-- Последняя страница -->
        <button
          v-if="showLastPage"
          @click="goToPage(totalPages)"
          :aria-label="`Перейти на страницу ${totalPages}`"
          :aria-current="currentPageModel === totalPages ? 'page' : undefined"
          class="min-w-[32px] px-2 py-1.5 text-sm rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
          :class="currentPageModel === totalPages
            ? 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
            : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'"
        >
          {{ totalPages }}
        </button>
      </div>
      
      <button
        @click="goToPage(currentPageModel + 1)"
        :disabled="currentPageModel === totalPages"
        :aria-label="'Перейти на следующую страницу'"
        class="px-3 py-1.5 text-sm rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
        :class="currentPageModel === totalPages
          ? 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-dim)]'
          : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--bg-elevated)]'"
      >
        <span class="sr-only">Вперед</span>
        <span aria-hidden="true">›</span>
      </button>
    </div>
    
    <div class="flex items-center gap-2 order-2 sm:order-3">
      <label for="pagination-per-page" class="text-xs text-[color:var(--text-dim)]">На странице:</label>
      <select
        id="pagination-per-page"
        :value="perPageModel"
        @change="onPerPageChange(Number(($event.target as HTMLSelectElement).value))"
        class="h-7 px-2 text-xs rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] focus:border-[color:var(--accent-green)] focus:outline-none focus:ring-2 focus:ring-[color:var(--focus-ring)] focus:ring-offset-2 focus:ring-offset-[color:var(--bg-main)]"
        aria-label="Количество элементов на странице"
      >
        <option :value="10">10</option>
        <option :value="25">25</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
      </select>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'

interface Props {
  currentPage: number
  perPage: number
  total: number
}

const props = withDefaults(defineProps<Props>(), {
  currentPage: 1,
  perPage: 25,
  total: 0
})

const emit = defineEmits<{
  'update:currentPage': [page: number]
  'update:perPage': [perPage: number]
}>()

// Валидированные модели с защитой от некорректных значений
const currentPageModel = computed({
  get() {
    const validPage = Math.max(1, Math.min(props.currentPage, totalPages.value || 1))
    if (validPage !== props.currentPage) {
      // Автоматически исправляем некорректное значение
      emit('update:currentPage', validPage)
    }
    return validPage
  },
  set(value: number) {
    const validPage = Math.max(1, Math.min(value, totalPages.value || 1))
    emit('update:currentPage', validPage)
  }
})

const perPageModel = computed({
  get() {
    const validPerPage = Math.max(1, Math.min(props.perPage, 100))
    if (validPerPage !== props.perPage) {
      emit('update:perPage', validPerPage)
    }
    return validPerPage
  },
  set(value: number) {
    const validPerPage = Math.max(1, Math.min(value, 100))
    emit('update:perPage', validPerPage)
  }
})

const totalPages = computed(() => {
  if (props.total <= 0 || perPageModel.value <= 0) return 0
  return Math.ceil(props.total / perPageModel.value)
})

const startItem = computed(() => {
  if (props.total === 0) return 0
  const start = (currentPageModel.value - 1) * perPageModel.value + 1
  return Math.min(start, props.total)
})

const endItem = computed(() => {
  if (props.total === 0) return 0
  const end = currentPageModel.value * perPageModel.value
  return Math.min(end, props.total)
})

const visiblePages = computed(() => {
  const pages: number[] = []
  if (totalPages.value === 0) return pages
  
  const maxVisible = 5
  const current = currentPageModel.value
  const total = totalPages.value
  
  let start = Math.max(1, current - Math.floor(maxVisible / 2))
  let end = Math.min(total, start + maxVisible - 1)
  
  // Корректируем начало, если конец достигнут
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }
  
  // Исключаем первую и последнюю страницы, если они показываются отдельно
  const firstPage = 1
  const lastPage = total
  
  for (let i = start; i <= end; i++) {
    if (i !== firstPage && i !== lastPage) {
      pages.push(i)
    }
  }
  
  return pages
})

const showFirstPage = computed(() => {
  if (totalPages.value === 0) return false
  const firstInVisible = visiblePages.value[0] || totalPages.value + 1
  return firstInVisible > 2
})

const showLastPage = computed(() => {
  if (totalPages.value === 0) return false
  const lastInVisible = visiblePages.value[visiblePages.value.length - 1] || 0
  return lastInVisible < totalPages.value - 1
})

const showFirstEllipsis = computed(() => {
  if (!showFirstPage.value) return false
  const firstInVisible = visiblePages.value[0] || totalPages.value + 1
  return firstInVisible > 3
})

const showLastEllipsis = computed(() => {
  if (!showLastPage.value) return false
  const lastInVisible = visiblePages.value[visiblePages.value.length - 1] || 0
  return lastInVisible < totalPages.value - 2
})

// Автоматически корректируем текущую страницу при изменении perPage
watch(() => props.perPage, (newPerPage, oldPerPage) => {
  if (oldPerPage && newPerPage !== oldPerPage) {
    // Пересчитываем текущую страницу, чтобы остаться в пределах
    const newTotalPages = Math.ceil(props.total / newPerPage)
    if (currentPageModel.value > newTotalPages && newTotalPages > 0) {
      emit('update:currentPage', newTotalPages)
    }
  }
})

function goToPage(page: number) {
  const validPage = Math.max(1, Math.min(page, totalPages.value || 1))
  if (validPage !== currentPageModel.value) {
    currentPageModel.value = validPage
  }
}

function onPerPageChange(newPerPage: number) {
  const validPerPage = Math.max(1, Math.min(newPerPage, 100))
  perPageModel.value = validPerPage
  // Переходим на первую страницу при изменении размера страницы
  if (currentPageModel.value !== 1) {
    emit('update:currentPage', 1)
  }
}
</script>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
