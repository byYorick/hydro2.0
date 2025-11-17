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

    <div class="rounded-xl border border-neutral-800 max-h-[720px] overflow-y-auto p-3" @scroll.passive="onScroll">
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
        <ZoneCard v-for="z in windowedZones" :key="z.id" :zone="z" :telemetry="z.telemetry" />
      </div>
      <div v-if="!filteredZones.length" class="text-sm text-neutral-400 px-1 py-6">Нет зон по текущим фильтрам</div>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, ref } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { usePage } from '@inertiajs/vue3'
import { translateStatus } from '@/utils/i18n'

const page = usePage()
const zones = computed(() => page.props.zones || [])

const status = ref('')
const query = ref('')

const filteredZones = computed(() => {
  return zones.value.filter((z) => {
    const okStatus = status.value ? z.status === status.value : true
    const okQuery = query.value ? (z.name || '').toLowerCase().includes(query.value.toLowerCase()) : true
    return okStatus && okQuery
  })
})

// Простейшая виртуализация по окну
const start = ref(0)
const visibleCount = 20
const approxRowHeight = 160 // px
function onScroll(ev) {
  const top = ev.target.scrollTop || 0
  start.value = Math.max(0, Math.floor(top / approxRowHeight) * 2) // грубая оценка для 2 колоночной сетки
}
const windowedZones = computed(() => filteredZones.value.slice(start.value, start.value + visibleCount))
</script>

