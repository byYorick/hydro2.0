<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-5 shadow-[var(--shadow-card)]">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">мониторинг зон</p>
            <h1 class="text-2xl font-semibold tracking-tight mt-1">Зоны выращивания</h1>
            <p class="text-sm text-[color:var(--text-dim)] mt-1">Статусы, быстрые действия и сравнение зон.</p>
          </div>
          <div class="flex flex-wrap gap-2 justify-end">
            <Button
              size="sm"
              variant="secondary"
              @click="showComparisonModal = true"
              :disabled="filteredZones.length < 2"
            >
              📊 Сравнить зоны
            </Button>
          </div>
        </div>
        <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-4">
          <div class="glass-panel border border-[color:var(--badge-success-border)] rounded-xl p-3 shadow-[inset_0_0_0_1px_var(--badge-success-border)]">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">Активные</div>
            <div class="text-3xl font-semibold text-[color:var(--accent-green)]">{{ runningCount }}</div>
          </div>
          <div class="glass-panel border border-[color:var(--border-muted)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">Пауза</div>
            <div class="text-3xl font-semibold text-[color:var(--text-primary)]">{{ pausedCount }}</div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-warning-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">Warning</div>
            <div class="text-3xl font-semibold text-[color:var(--accent-amber)]">{{ warningCount }}</div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-danger-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">Alarm</div>
            <div class="text-3xl font-semibold text-[color:var(--accent-red)]">{{ alarmCount }}</div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-info-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">Всего</div>
            <div class="text-3xl font-semibold text-[color:var(--accent-cyan)]">{{ totalZones }}</div>
          </div>
        </div>
      </div>

      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4 shadow-[var(--shadow-card)]">
        <div class="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
          <div class="flex items-center gap-2 flex-1 sm:flex-none">
            <label class="text-sm text-[color:var(--text-muted)] shrink-0">Статус:</label>
            <select v-model="status" class="input-select h-10 flex-1 sm:w-auto sm:min-w-[160px]">
              <option value="">Все</option>
              <option value="RUNNING">Запущено</option>
              <option value="PAUSED">Приостановлено</option>
              <option value="WARNING">Предупреждение</option>
              <option value="ALARM">Тревога</option>
            </select>
          </div>
          <div class="flex items-center gap-2 flex-1 sm:flex-none">
            <label class="text-sm text-[color:var(--text-muted)] shrink-0">Поиск:</label>
            <input v-model="query" placeholder="Имя зоны..." class="input-field h-10 flex-1 sm:w-64" />
          </div>
          <div class="flex items-center gap-2 flex-1 sm:flex-none">
            <button
              @click="showOnlyFavorites = !showOnlyFavorites"
              class="h-10 px-3 rounded-lg border text-sm transition-colors flex items-center gap-1.5 bg-[color:var(--bg-surface-strong)]"
              :class="showOnlyFavorites
                ? 'border-[color:var(--badge-warning-border)] text-[color:var(--accent-amber)] shadow-[0_0_0_1px_var(--badge-warning-border)]'
                : 'border-[color:var(--border-muted)] text-[color:var(--text-primary)] hover:border-[color:var(--border-strong)]'"
            >
              <svg
                class="w-4 h-4"
                :class="showOnlyFavorites ? 'fill-[color:var(--accent-amber)]' : ''"
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
      </div>

      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl overflow-hidden shadow-[var(--shadow-card)] max-h-[720px] flex flex-col">
        <div class="overflow-auto flex-1">
          <table class="w-full border-collapse">
            <thead class="bg-[color:var(--bg-surface-strong)] text-[color:var(--text-primary)] text-sm sticky top-0 z-10 backdrop-blur-md">
              <tr>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">
                  <div class="flex items-center gap-2">
                    <div class="w-5"></div>
                    <span>Название</span>
                  </div>
                </th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">Статус</th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">Теплица</th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">pH</th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">EC</th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">Температура</th>
                <th class="text-left px-4 py-3 font-semibold border-b border-[color:var(--border-muted)]">Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(r, index) in rows"
                :key="r[0]"
                :class="index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]'"
                class="text-sm border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)] transition-colors"
              >
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2 min-w-0">
                    <button
                      @click.stop="toggleZoneFavorite(getZoneIdFromRow(r))"
                      class="p-1 rounded-md hover:bg-[color:var(--bg-elevated)] transition-colors shrink-0 w-8 h-8 flex items-center justify-center"
                      :title="isZoneFavorite(getZoneIdFromRow(r)) ? 'Удалить из избранного' : 'Добавить в избранное'"
                    >
                      <svg
                        class="w-4 h-4 transition-colors"
                        :class="isZoneFavorite(getZoneIdFromRow(r)) ? 'text-[color:var(--accent-amber)] fill-[color:var(--accent-amber)]' : 'text-[color:var(--text-dim)]'"
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
                    <Link :href="`/zones/${r[0]}`" class="text-[color:var(--accent-cyan)] hover:underline truncate min-w-0 font-semibold">{{ r[1] }}</Link>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <Badge :variant="getStatusVariant(r[2])" class="shrink-0">{{ r[2] }}</Badge>
                </td>
                <td class="px-4 py-3 text-xs text-[color:var(--text-muted)]">
                  <span class="truncate block">{{ r[3] || '-' }}</span>
                </td>
                <td class="px-4 py-3 text-xs text-[color:var(--text-muted)]">{{ r[4] || '-' }}</td>
                <td class="px-4 py-3 text-xs text-[color:var(--text-muted)]">{{ r[5] || '-' }}</td>
                <td class="px-4 py-3 text-xs text-[color:var(--text-muted)]">{{ r[6] || '-' }}</td>
                <td class="px-4 py-3">
                  <Link :href="`/zones/${r[0]}`">
                    <Button size="sm" variant="secondary">Подробнее</Button>
                  </Link>
                </td>
              </tr>
              <tr v-if="!rows.length">
                <td colspan="7" class="px-4 py-6 text-sm text-[color:var(--text-dim)] text-center">Нет зон по текущим фильтрам</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pagination
          v-model:current-page="currentPage"
          v-model:per-page="perPage"
          :total="filteredZones.length"
        />
      </div>

      <!-- Модальное окно сравнения зон -->
      <ZoneComparisonModal
        :open="showComparisonModal"
        :zones="filteredZones"
        @close="showComparisonModal = false"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { router, Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneComparisonModal from '@/Components/ZoneComparisonModal.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Pagination from '@/Components/Pagination.vue'
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

const totalZones = computed(() => zones.value.length || 0)
const runningCount = computed(() => zones.value.filter((z) => z.status === 'RUNNING').length)
const pausedCount = computed(() => zones.value.filter((z) => z.status === 'PAUSED').length)
const warningCount = computed(() => zones.value.filter((z) => z.status === 'WARNING').length)
const alarmCount = computed(() => zones.value.filter((z) => z.status === 'ALARM').length)

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
const currentPage = ref<number>(1)
const perPage = ref<number>(25)

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

// Пагинированные зоны
const paginatedZones = computed(() => {
  const total = filteredZones.value.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filteredZones.value.slice(start, end)
})

// Преобразуем зоны в строки таблицы
const rows = computed(() => {
  return paginatedZones.value.map(z => {
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

// Сбрасываем на первую страницу при изменении фильтров
watch([status, query, showOnlyFavorites], () => {
  currentPage.value = 1
})

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

th:nth-child(3),
td:nth-child(3) {
  min-width: 120px;
  max-width: 200px;
}

th:nth-child(4),
td:nth-child(4),
th:nth-child(5),
td:nth-child(5) {
  min-width: 60px;
  text-align: center;
}

th:nth-child(6),
td:nth-child(6) {
  min-width: 100px;
}

th:last-child,
td:last-child {
  min-width: 120px;
  text-align: center;
}
</style>
