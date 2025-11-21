<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Зоны</h1>

    <div class="mb-3 flex flex-wrap items-center gap-2">
      <label class="text-sm text-neutral-300">Статус:</label>
      <select v-model="status" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
        <option value="">Все</option>
        <option value="RUNNING">Запущено</option>
        <option value="PAUSED">Приостановлено</option>
        <option value="WARNING">Предупреждение</option>
        <option value="ALARM">Тревога</option>
      </select>
      <label class="ml-4 text-sm text-neutral-300">Поиск:</label>
      <input v-model="query" placeholder="Имя зоны..." class="h-9 w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
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
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onUnmounted, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { usePage } from '@inertiajs/vue3'
import { useZonesStore } from '@/stores/zones'
import { useStoreEvents } from '@/composables/useStoreEvents'
import { translateStatus } from '@/utils/i18n'
import type { Zone } from '@/types'

const page = usePage<{ zones?: Zone[] }>()
const zonesStore = useZonesStore()
const { subscribeWithCleanup } = useStoreEvents()

// Инициализируем store из props
zonesStore.initFromProps(page.props)

// Используем getter allZones для получения всех зон
const zones = computed(() => zonesStore.allZones)

// Автоматическая синхронизация через события stores
onMounted(() => {
  // Слушаем события обновления зон для автоматического обновления списка
  subscribeWithCleanup('zone:updated', (zone: Zone) => {
    // Обновляем зону в store
    zonesStore.upsert(zone)
  })
  
  // Слушаем события создания зон
  subscribeWithCleanup('zone:created', (zone: Zone) => {
    zonesStore.upsert(zone)
  })
  
  // Слушаем события удаления зон
  subscribeWithCleanup('zone:deleted', (zoneId: number) => {
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

// Реакция на изменения в store для обновления списка зон
watch(() => zonesStore.cacheVersion, () => {
  // При изменении cacheVersion можно выполнить частичный reload для синхронизации
  // Но лучше обновить через Inertia только если зоны действительно изменились
})

const status = ref<string>('')
const query = ref<string>('')

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
    return okStatus && okQuery
  })
})

// Виртуализация через DynamicScroller (для элементов переменной высоты)
const approxRowHeight = 160 // px
</script>

