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

    <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
      <!-- Заголовок таблицы -->
      <div class="flex-shrink-0 grid grid-cols-7 gap-0 bg-neutral-900 text-neutral-300 text-sm border-b border-neutral-800">
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
            class="grid grid-cols-7 gap-0 text-sm border-b border-neutral-900"
            style="height:44px"
          >
            <div class="px-3 py-2 flex items-center gap-2">
              <button
                @click.stop="toggleZoneFavorite(getZoneIdFromRow(r))"
                class="p-0.5 rounded hover:bg-neutral-800 transition-colors shrink-0"
                :title="isZoneFavorite(getZoneIdFromRow(r)) ? 'Удалить из избранного' : 'Добавить в избранное'"
              >
                <svg
                  class="w-3.5 h-3.5 transition-colors"
                  :class="isZoneFavorite(getZoneIdFromRow(r)) ? 'text-amber-400 fill-amber-400' : 'text-neutral-600'"
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
              </button>
              <Link :href="`/zones/${r[0]}`" class="text-sky-400 hover:underline">{{ r[1] }}</Link>
            </div>
            <div class="px-3 py-2 flex items-center">
              <Badge :variant="getStatusVariant(r[2])">{{ r[2] }}</Badge>
            </div>
            <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[3] || '-' }}</div>
            <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[4] || '-' }}</div>
            <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[5] || '-' }}</div>
            <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[6] || '-' }}</div>
            <div class="px-3 py-2 flex items-center">
              <Link :href="`/zones/${r[0]}`">
                <Button size="sm" variant="secondary">Подробнее</Button>
              </Link>
            </div>
          </div>
        </RecycleScroller>
        <div v-if="!rows.length" class="text-sm text-neutral-400 px-3 py-6">Нет зон по текущим фильтрам</div>
      </div>
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
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { router, Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneComparisonModal from '@/Components/ZoneComparisonModal.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useZonesStore } from '@/stores/zones'
import { useStoreEvents } from '@/composables/useStoreEvents'
import { useBatchUpdates } from '@/composables/useOptimizedUpdates'
import { useFavorites } from '@/composables/useFavorites'
import { translateStatus } from '@/utils/i18n'
import type { Zone } from '@/types'

const headers = ['Название', 'Статус', 'Теплица', 'pH', 'EC', 'Температура', 'Действия']
const page = usePage<{ zones?: Zone[] }>()
const zonesStore = useZonesStore()
const { subscribeWithCleanup } = useStoreEvents()

// Инициализируем store из props
zonesStore.initFromProps(page.props)

// Используем getter allZones для получения всех зон
const zones = computed(() => zonesStore.allZones)

// Оптимизированные batch updates для обновлений зон
// Используем silent: true чтобы предотвратить рекурсию (события уже были эмитнуты извне)
const { add: addZoneUpdate, flush: flushZoneUpdates } = useBatchUpdates<Zone>(
  (zones) => {
    // Применяем обновления пакетом с silent: true чтобы не создавать новый цикл событий
    zones.forEach(zone => {
      zonesStore.upsert(zone, true)
    })
  },
  { debounceMs: 150, maxBatchSize: 10, maxWaitMs: 500 }
)

// Автоматическая синхронизация через события stores
onMounted(() => {
  // Слушаем события обновления зон для автоматического обновления списка
  // Используем silent: true чтобы предотвратить рекурсию (события уже были эмитнуты)
  subscribeWithCleanup('zone:updated', (zone: Zone) => {
    // Используем batch updates для оптимизации
    // В обработчике событий используем silent: true чтобы не создавать новый цикл событий
    addZoneUpdate(zone)
  })
  
  // Слушаем события создания зон
  subscribeWithCleanup('zone:created', (zone: Zone) => {
    // Создание зон применяем сразу с silent: true
    zonesStore.upsert(zone, true)
  })
  
  // Слушаем события удаления зон
  subscribeWithCleanup('zone:deleted', (zoneId: number) => {
    // Удаление применяем сразу
    zonesStore.remove(zoneId)
  })
  
  // Слушаем события присвоения рецептов к зонам
  subscribeWithCleanup('zone:recipe:attached', async ({ zoneId }: { zoneId: number; recipeId: number }) => {
    // Инвалидируем кеш
    zonesStore.invalidateCache()
    
      // Обновляем зону через API и store вместо reload для сохранения фильтров и scroll
      try {
        const { useZones } = await import('@/composables/useZones')
        const { fetchZone } = useZones()
        const updatedZone = await fetchZone(zoneId, true) // forceRefresh = true
        if (updatedZone?.id) {
          // Используем silent: false здесь, так как это прямое обновление из API, не из события
          zonesStore.upsert(updatedZone, false)
        }
    } catch (error) {
      // Fallback к частичному reload при ошибке
      router.reload({ only: ['zones'], preserveScroll: true })
    }
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

const { isZoneFavorite, toggleZoneFavorite } = useFavorites()

// Оптимизируем фильтрацию: мемоизируем нижний регистр запроса
const queryLower = computed(() => query.value.toLowerCase())
const filteredZones = computed(() => {
  const statusFilter = status.value
  const queryFilter = queryLower.value
  
  if (!statusFilter && !queryFilter && !showOnlyFavorites.value) {
    return zones.value // Если фильтров нет, возвращаем все зоны без фильтрации
  }
  
  return zones.value.filter((z) => {
    const okStatus = statusFilter ? z.status === statusFilter : true
    const okQuery = queryFilter ? (z.name || '').toLowerCase().includes(queryFilter) : true
    const okFavorites = showOnlyFavorites.value ? isZoneFavorite(z.id) : true
    return okStatus && okQuery && okFavorites
  })
})

// Преобразуем зоны в строки таблицы
const rows = computed(() => {
  return filteredZones.value.map(z => {
    // Безопасное форматирование чисел
    const formatNumber = (value: unknown, decimals: number): string => {
      if (value === null || value === undefined) return '-'
      const num = typeof value === 'number' ? value : Number(value)
      return !isNaN(num) && isFinite(num) ? num.toFixed(decimals) : '-'
    }
    
    return [
      z.id,
      z.name || '-',
      translateStatus(z.status),
      z.greenhouse?.name || '-',
      formatNumber(z.telemetry?.ph, 2),
      formatNumber(z.telemetry?.ec, 1),
      z.telemetry?.temperature !== null && z.telemetry?.temperature !== undefined 
        ? (() => {
            const temp = typeof z.telemetry.temperature === 'number' 
              ? z.telemetry.temperature 
              : Number(z.telemetry.temperature)
            return !isNaN(temp) && isFinite(temp) ? `${temp.toFixed(1)}°C` : '-'
          })()
        : '-',
      z.id // Добавляем ID в конец для удобства доступа
    ]
  })
})

// Функция для получения ID зоны из строки таблицы
function getZoneIdFromRow(row: (string | number)[]): number {
  // Последний элемент строки - это ID
  const id = row[row.length - 1]
  return typeof id === 'number' ? id : 0
}

// Функция для получения варианта Badge по статусу
function getStatusVariant(status: string): string {
  switch (status) {
    case 'Запущено':
      return 'success'
    case 'Приостановлено':
      return 'neutral'
    case 'Предупреждение':
      return 'warning'
    case 'Тревога':
      return 'danger'
    default:
      return 'neutral'
  }
}

// Виртуализация через RecycleScroller
const rowHeight = 44
</script>

