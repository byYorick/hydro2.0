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
        <option value="sensor">Датчик</option>
        <option value="actuator">Актуатор</option>
        <option value="controller">Контроллер</option>
      </select>
      <label class="ml-4 text-sm text-neutral-300">Поиск:</label>
      <input v-model="query" placeholder="ID устройства..." class="h-9 w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
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
            <div class="px-3 py-2 flex items-center">
              <Link :href="`/devices/${r[0]}`" class="text-sky-400 hover:underline">{{ r[0] }}</Link>
            </div>
            <div class="px-3 py-2 flex items-center">{{ r[1] }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[2] }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[3] }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[4] }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[5] }}</div>
            <div class="px-3 py-2 flex items-center">{{ r[6] }}</div>
          </div>
        </RecycleScroller>
        <div v-if="!rows.length" class="text-sm text-neutral-400 px-3 py-6">Нет устройств по текущим фильтрам</div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import DataTable from '@/Components/DataTable.vue'
import Button from '@/Components/Button.vue'
import { useDevicesStore } from '@/stores/devices'
import { translateDeviceType, translateStatus } from '@/utils/i18n'
import type { Device } from '@/types'

const headers = ['UID', 'Зона', 'Имя', 'Тип', 'Статус', 'Версия ПО', 'Последний раз видели']
const page = usePage<{ devices?: Device[] }>()
const devicesStore = useDevicesStore()
onMounted(() => devicesStore.initFromProps(page.props))
const type = ref<string>('')
const query = ref<string>('')

// Оптимизируем фильтрацию: мемоизируем нижний регистр запроса
const queryLower = computed(() => query.value.toLowerCase())
const filtered = computed(() => {
  const typeFilter = type.value
  const queryFilter = queryLower.value
  
  if (!typeFilter && !queryFilter) {
    return devicesStore.items // Если фильтров нет, возвращаем все устройства
  }
  
  return devicesStore.items.filter(d => {
    const okType = typeFilter ? d.type === typeFilter : true
    const okQuery = queryFilter ? (d.uid || d.name || '').toLowerCase().includes(queryFilter) : true
    return okType && okQuery
  })
})

const rows = computed(() => filtered.value.map(d => [
  d.uid || d.id,
  d.zone?.name || '-',
  d.name || '-',
  d.type ? translateDeviceType(d.type) : '-',
  d.status ? translateStatus(d.status) : 'неизвестно',
  d.fw_version || '-',
  d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('ru-RU') : '-'
]))

// Виртуализация через RecycleScroller
const rowHeight = 44
</script>

