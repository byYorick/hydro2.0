<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-lg font-semibold">Устройства</h1>
      <Link href="/devices/add">
        <Button size="sm" variant="primary">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Добавить ноду
        </Button>
      </Link>
    </div>
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <label class="text-sm text-neutral-300">Тип:</label>
      <select v-model="type" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
        <option value="">Все</option>
        <option value="sensor">Sensor</option>
        <option value="actuator">Actuator</option>
        <option value="controller">Controller</option>
      </select>
      <label class="ml-4 text-sm text-neutral-300">Поиск:</label>
      <input v-model="query" placeholder="ID устройства..." class="h-9 w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
    </div>
    <div class="rounded-xl border border-neutral-800 overflow-y-auto max-h-[720px]" @scroll.passive="onScroll">
      <table class="min-w-full text-sm">
        <thead class="bg-neutral-900 text-neutral-300">
          <tr>
            <th v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium border-b border-neutral-800">
              {{ h }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in windowed" :key="r[0]" class="odd:bg-neutral-950 even:bg-neutral-925" style="height:44px">
            <td class="px-3 py-2 border-b border-neutral-900">
              <Link :href="`/devices/${r[0]}`" class="text-sky-400 hover:underline">{{ r[0] }}</Link>
            </td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ r[1] }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ r[2] }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ r[3] }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ r[4] }}</td>
            <td class="px-3 py-2 border-b border-neutral-900">{{ r[5] }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!rows.length" class="text-sm text-neutral-400 px-3 py-6">Нет устройств по текущим фильтрам</div>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import DataTable from '@/Components/DataTable.vue'
import Button from '@/Components/Button.vue'
import { useDevicesStore } from '@/stores/devices'

const headers = ['UID', 'Зона', 'Имя', 'Тип', 'Статус', 'Версия ПО', 'Последний раз видели']
const page = usePage()
const devicesStore = useDevicesStore()
onMounted(() => devicesStore.initFromProps(page.props))
const type = ref('')
const query = ref('')

const filtered = computed(() => {
  return devicesStore.items.filter(d => {
    const okType = type.value ? d.type === type.value : true
    const okQuery = query.value ? (d.uid || d.name || '').toLowerCase().includes(query.value.toLowerCase()) : true
    return okType && okQuery
  })
})

const rows = computed(() => filtered.value.map(d => [
  d.uid || d.id,
  d.zone?.name || '-',
  d.name || '-',
  d.type || '-',
  d.status || 'unknown',
  d.fw_version || '-',
  d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('ru-RU') : '-'
]))

// Виртуализация
const start = ref(0)
const visibleCount = 30
const rowHeight = 44
function onScroll(ev) {
  const top = ev.target.scrollTop || 0
  start.value = Math.max(0, Math.floor(top / rowHeight) - 2)
}
const windowed = computed(() => rows.value.slice(start.value, start.value + visibleCount))
</script>

