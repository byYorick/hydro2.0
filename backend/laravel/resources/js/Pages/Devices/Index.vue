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
    <div class="mb-3 flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2">
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Тип:</label>
        <select v-model="type" class="h-9 flex-1 sm:w-auto sm:min-w-[140px] rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option value="">Все</option>
          <option value="sensor">Датчик</option>
          <option value="actuator">Актуатор</option>
          <option value="controller">Контроллер</option>
        </select>
      </div>
      <div class="flex items-center gap-2 flex-1 sm:flex-none">
        <label class="text-sm text-neutral-300 shrink-0">Поиск:</label>
        <input v-model="query" placeholder="ID устройства..." class="h-9 flex-1 sm:w-56 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
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
                @click.stop="toggleDeviceFavorite(getDeviceIdFromRow(r))"
                class="p-0.5 rounded hover:bg-neutral-800 transition-colors shrink-0"
                :title="isDeviceFavorite(getDeviceIdFromRow(r)) ? 'Удалить из избранного' : 'Добавить в избранное'"
              >
                <svg
                  class="w-3.5 h-3.5 transition-colors"
                  :class="isDeviceFavorite(getDeviceIdFromRow(r)) ? 'text-amber-400 fill-amber-400' : 'text-neutral-600'"
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
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import DataTable from '@/Components/DataTable.vue'
import Button from '@/Components/Button.vue'
import { useDevicesStore } from '@/stores/devices'
import { useStoreEvents } from '@/composables/useStoreEvents'
import { useFavorites } from '@/composables/useFavorites'
import { translateDeviceType, translateStatus } from '@/utils/i18n'
import type { Device } from '@/types'
import { logger } from '@/utils/logger'

const headers = ['UID', 'Зона', 'Имя', 'Тип', 'Статус', 'Версия ПО', 'Последний раз видели']
const page = usePage<{ devices?: Device[] }>()
const devicesStore = useDevicesStore()
const { subscribeWithCleanup } = useStoreEvents()

onMounted(() => {
  devicesStore.initFromProps(page.props)
  
  // Автоматическая синхронизация через события stores
  // Слушаем события обновления устройств
  subscribeWithCleanup('device:updated', (device: Device) => {
    devicesStore.upsert(device)
  })
  
  // Слушаем события создания устройств
  subscribeWithCleanup('device:created', (device: Device) => {
    devicesStore.upsert(device)
  })
  
  // Слушаем события удаления устройств
  subscribeWithCleanup('device:deleted', (deviceId: number | string) => {
    devicesStore.remove(deviceId)
  })
  
  // Слушаем события lifecycle переходов
  subscribeWithCleanup('device:lifecycle:transitioned', ({ deviceId }: { deviceId: number; fromState: string; toState: string }) => {
    // Инвалидируем кеш при lifecycle переходе
    devicesStore.invalidateCache()
    // Можно выполнить частичный reload для синхронизации
    router.reload({ only: ['devices'], preserveScroll: true })
  })
  
  // Подписка на WebSocket события обновления устройств
  if (window.Echo) {
    try {
      const channel = window.Echo.channel('hydro.devices')
      
      // Слушаем события обновления устройств
      // Используем broadcastAs имя 'device.updated'
      channel.listen('.device.updated', (event: any) => {
        logger.debug('[Devices/Index] Received device update via WebSocket', event)
        
        if (event.device) {
          const device = event.device as Device
          // Обновляем устройство в store
          devicesStore.upsert(device)
          
          // Если это новое устройство, эмитим событие создания
          if (event.device.was_recently_created) {
            logger.info('[Devices/Index] New device created:', device.uid)
          }
        }
      })
      
      logger.debug('[Devices/Index] Subscribed to hydro.devices WebSocket channel')
      
      // Очистка при размонтировании
      onUnmounted(() => {
        channel.stopListening('.device.updated')
        if (typeof channel.leave === 'function') {
          channel.leave()
        }
      })
    } catch (err) {
      logger.error('[Devices/Index] Failed to subscribe to devices WebSocket:', err)
    }
  } else {
    logger.warn('[Devices/Index] Echo not available, skipping WebSocket subscription')
  }
})
const type = ref<string>('')
const query = ref<string>('')
const showOnlyFavorites = ref<boolean>(false)

const { isDeviceFavorite, toggleDeviceFavorite } = useFavorites()

// Оптимизируем фильтрацию: мемоизируем нижний регистр запроса
const queryLower = computed(() => query.value.toLowerCase())
const filtered = computed(() => {
  const typeFilter = type.value
  const queryFilter = queryLower.value
  
  // Используем геттер allDevices для получения массива устройств
  const devices = devicesStore.allDevices
  
  if (!Array.isArray(devices)) {
    return []
  }
  
  return devices.filter(d => {
    const okType = typeFilter ? d.type === typeFilter : true
    const okQuery = queryFilter ? (d.uid || d.name || '').toLowerCase().includes(queryFilter) : true
    const okFavorites = showOnlyFavorites.value ? isDeviceFavorite(d.id) : true
    return okType && okQuery && okFavorites
  })
})

const rows = computed(() => {
  if (!Array.isArray(filtered.value)) {
    return []
  }
  return filtered.value.map(d => [
  d.uid || d.id,
  d.zone?.name || '-',
  d.name || '-',
  d.type ? translateDeviceType(d.type) : '-',
  d.status ? translateStatus(d.status) : 'неизвестно',
  d.fw_version || '-',
  d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('ru-RU') : '-',
  d.id // Добавляем ID в конец для удобства доступа
  ])
})

// Функция для получения ID устройства из строки таблицы
function getDeviceIdFromRow(row: (string | number)[]): number {
  // Последний элемент строки - это ID
  const id = row[row.length - 1]
  return typeof id === 'number' ? id : 0
}

// Виртуализация через RecycleScroller
const rowHeight = 44
</script>

