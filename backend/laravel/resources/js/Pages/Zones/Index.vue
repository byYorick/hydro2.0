<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">Зоны</h1>
      <Button
        size="sm"
        variant="secondary"
        @click="showComparisonModal = true"
        :disabled="filteredZones.length < 2"
      >
        📊 Сравнить зоны
      </Button>
    </div>

    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Статус:</label>
        <select v-model="status" class="h-9 flex-1 sm:w-auto sm:min-w-[140px] rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option value="">Все</option>
          <option value="RUNNING">Запущено</option>
          <option value="PAUSED">Приостановлено</option>
          <option value="WARNING">Предупреждение</option>
          <option value="ALARM">Тревога</option>
        </select>
      </div>
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Поиск:</label>
        <input v-model="query" placeholder="Имя зоны..." class="h-9 flex-1 sm:w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
      </div>
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <button
          @click="showOnlyFavorites = !showOnlyFavorites"
          class="h-9 px-3 rounded-md border text-sm transition-colors flex items-center gap-1.5"
          :class="showOnlyFavorites
            ? 'border-amber-500 bg-amber-950/30 text-amber-300'
            : 'border-neutral-700 bg-neutral-900 text-neutral-300 hover:border-neutral-600'"
        >
          <svg
            class="w-4 h-4"
            :class="showOnlyFavorites ? 'fill-amber-400' : ''"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
            />
          </svg>
          <span>Избранные</span>
        </button>
      </div>
    </div>

    <div class="rounded-xl border border-neutral-800 max-h-[720px] overflow-hidden p-3">
      <DynamicScroller
        :items="filteredZones"
        :min-item-size="approxRowHeight"
        key-field="id"
        class="h-full"
        v-slot="{ item: z, index, active }"
      >
        <DynamicScrollerItem
          :item="z"
          :active="active"
          :data-index="index"
          :size-dependencies="[z.name, z.status]"
        >
          <ZoneCard :zone="z" :telemetry="z.telemetry" />
        </DynamicScrollerItem>
      </DynamicScroller>
      <div v-if="!filteredZones.length" class="text-sm text-neutral-400 px-1 py-6">Нет зон по текущим фильтрам</div>
    </div>

    <!-- Модальное окно сравнения зон -->
    <ZoneComparisonModal
      :open="showComparisonModal"
      :zones="filteredZones"
      @close="showComparisonModal = false"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onUnmounted, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import ZoneComparisonModal from '@/Components/ZoneComparisonModal.vue'
import Button from '@/Components/Button.vue'
import { usePage } from '@inertiajs/vue3'
import { useZonesStore } from '@/stores/zones'
import { useStoreEvents } from '@/composables/useStoreEvents'
import { useBatchUpdates } from '@/composables/useOptimizedUpdates'
import { useFavorites } from '@/composables/useFavorites'
import { translateStatus } from '@/utils/i18n'
import type { Zone } from '@/types'

const page = usePage<{ zones?: Zone[] }>()
const zonesStore = useZonesStore()
const { subscribeWithCleanup } = useStoreEvents()

// Инициализируем store из props
zonesStore.initFromProps(page.props)

// Используем getter allZones для получения всех зон
const zones = computed(() => zonesStore.allZones)

// Оптимизированные batch updates для обновлений зон
const { add: addZoneUpdate, flush: flushZoneUpdates } = useBatchUpdates<Zone>(
  (zones) => {
    // Применяем обновления пакетом
    zones.forEach(zone => {
      zonesStore.upsert(zone)
    })
  },
  { debounceMs: 150, maxBatchSize: 10, maxWaitMs: 500 }
)

// Автоматическая синхронизация через события stores
onMounted(() => {
  // Слушаем события обновления зон для автоматического обновления списка
  subscribeWithCleanup('zone:updated', (zone: Zone) => {
    // Используем batch updates для оптимизации
    addZoneUpdate(zone)
  })
  
  // Слушаем события создания зон
  subscribeWithCleanup('zone:created', (zone: Zone) => {
    // Создание зон применяем сразу
    zonesStore.upsert(zone)
  })
  
  // Слушаем события удаления зон
  subscribeWithCleanup('zone:deleted', (zoneId: number) => {
    // Удаление применяем сразу
    zonesStore.remove(zoneId)
  })
  
  // Слушаем события присвоения рецептов к зонам
  subscribeWithCleanup('zone:recipe:attached', ({ zoneId }: { zoneId: number; recipeId: number }) => {
    // Инвалидируем кеш и обновляем зону
    zonesStore.invalidateCache()
    // Можно выполнить частичный reload, если нужно
    router.reload({ only: ['zones'], preserveScroll: true })
  })
})

// При размонтировании применяем все накопленные обновления
onUnmounted(() => {
  flushZoneUpdates()
})

// Реакция на изменения в store для обновления списка зон
watch(() => zonesStore.cacheVersion, () => {
  // При изменении cacheVersion можно выполнить частичный reload для синхронизации
  // Но лучше обновить через Inertia только если зоны действительно изменились
})

// Инициализация статуса из URL параметров
const urlParams = new URLSearchParams(window.location.search)
const status = ref<string>(urlParams.get('status') || '')
const query = ref<string>('')
const showComparisonModal = ref<boolean>(false)
const showOnlyFavorites = ref<boolean>(false)

const { isZoneFavorite } = useFavorites()

// Оптимизируем фильтрацию: мемоизируем нижний регистр запроса
const queryLower = computed(() => query.value.toLowerCase())
const filteredZones = computed(() => {
  const statusFilter = status.value
  const queryFilter = queryLower.value
  
  if (!statusFilter && !queryFilter) {
    return zones.value // Если фильтров нет, возвращаем все зоны без фильтрации
  }
  
  return zones.value.filter((z) => {
    const okStatus = statusFilter ? z.status === statusFilter : true
    const okQuery = queryFilter ? (z.name || '').toLowerCase().includes(queryFilter) : true
    const okFavorites = showOnlyFavorites.value ? isZoneFavorite(z.id) : true
    return okStatus && okQuery && okFavorites
  })
})

// Виртуализация через DynamicScroller (для элементов переменной высоты)
const approxRowHeight = 160 // px
</script>

