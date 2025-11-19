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
import { computed, ref, shallowRef } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { usePage } from '@inertiajs/vue3'
import { translateStatus } from '@/utils/i18n'
import type { Zone } from '@/types'

const page = usePage<{ zones?: Zone[] }>()
const zones = computed(() => (page.props.zones || []) as Zone[])

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

