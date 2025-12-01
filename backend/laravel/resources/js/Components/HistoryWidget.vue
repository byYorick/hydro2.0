<template>
  <Card v-if="hasHistory" class="mb-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold flex items-center gap-2">
        <svg class="w-4 h-4 text-neutral-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        История просмотров
      </h3>
      <button
        @click="clearAll"
        class="text-xs text-neutral-400 hover:text-neutral-200 transition-colors"
        title="Очистить историю"
      >
        Очистить
      </button>
    </div>

    <div class="space-y-2">
      <div
        v-for="item in recentHistory"
        :key="`${item.type}-${item.id}`"
        class="flex items-center justify-between p-2 rounded border border-neutral-800 hover:border-neutral-700 transition-colors group"
      >
        <Link
          :href="item.url"
          class="flex items-center gap-2 flex-1 min-w-0"
        >
          <span class="text-sm shrink-0">
            {{ item.type === 'zone' ? '🌱' : '🔌' }}
          </span>
          <span class="text-sm text-neutral-300 truncate group-hover:text-neutral-100 transition-colors">
            {{ item.name }}
          </span>
        </Link>
        <div class="flex items-center gap-2 shrink-0">
          <span class="text-xs text-neutral-500">
            {{ formatTimeAgo(item.timestamp) }}
          </span>
          <button
            @click.stop="removeItem(item.id, item.type)"
            class="p-1 rounded hover:bg-neutral-800 transition-colors text-neutral-500 hover:text-neutral-200"
            title="Удалить из истории"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div v-if="!hasHistory" class="text-xs text-neutral-500 text-center py-4">
      История просмотров пуста
      <div class="text-xs text-neutral-600 mt-1">
        Просмотренные зоны и устройства появятся здесь
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import { useHistory } from '@/composables/useHistory'
import { formatTimeAgo } from '@/utils/formatTime.js'

const {
  history,
  getRecentHistory,
  removeFromHistory,
  clearHistory,
} = useHistory()

const recentHistory = computed(() => getRecentHistory(10))
const hasHistory = computed(() => history.value.length > 0)

function removeItem(id: number, type: 'zone' | 'device'): void {
  removeFromHistory(id, type)
}

function clearAll(): void {
  if (confirm('Очистить всю историю просмотров?')) {
    clearHistory()
  }
}
</script>

