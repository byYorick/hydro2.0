<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader title="Устройства" subtitle="Список узлов, статусы и быстрые действия." eyebrow="инфраструктура">
        <template #actions>
          <Link href="/devices/add">
            <Button size="sm" variant="primary">
              <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              Добавить ноду
            </Button>
          </Link>
        </template>
      </PageHeader>

      <FilterBar>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Тип:</label>
          <select
            v-model="type"
            class="input-select flex-1 sm:w-auto sm:min-w-[140px]"
            data-testid="devices-filter-type"
          >
            <option value="">Все</option>
            <option value="sensor">Датчик</option>
            <option value="actuator">Актуатор</option>
            <option value="controller">Контроллер</option>
          </select>
        </div>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Поиск:</label>
          <input
            v-model="query"
            placeholder="ID устройства..."
            class="input-field flex-1 sm:w-56"
            data-testid="devices-filter-query"
          />
        </div>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <button
            @click="showOnlyFavorites = !showOnlyFavorites"
            class="h-9 px-3 rounded-md border text-sm transition-colors flex items-center gap-1.5 bg-[color:var(--bg-elevated)]"
            :class="showOnlyFavorites
              ? 'border-[color:var(--badge-warning-border)] text-[color:var(--accent-amber)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
            data-testid="devices-filter-favorites"
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
      </FilterBar>

      <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[720px] flex flex-col">
        <DataTableV2
          :columns="columns"
          :rows="paginatedData"
          empty-title="Нет устройств по текущим фильтрам"
          empty-description="Попробуйте изменить фильтры или дождитесь новых устройств."
          container-class="max-h-[720px]"
        >
          <template #cell-uid="{ row }">
            <div class="flex items-center gap-2 min-w-0">
              <button
                @click.stop="toggleDeviceFavorite(row.id)"
                class="p-0.5 rounded hover:bg-[color:var(--bg-surface-strong)] transition-colors shrink-0 w-5 h-5 flex items-center justify-center"
                :title="isDeviceFavorite(row.id) ? 'Удалить из избранного' : 'Добавить в избранное'"
              >
                <svg
                  class="w-3.5 h-3.5 transition-colors"
                  :class="isDeviceFavorite(row.id) ? 'text-[color:var(--accent-amber)] fill-[color:var(--accent-amber)]' : 'text-[color:var(--text-dim)]'"
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
              <Link :href="`/devices/${row.uid || row.id}`" class="text-[color:var(--accent-cyan)] hover:underline truncate min-w-0">{{ row.uid || row.id }}</Link>
            </div>
          </template>
          <template #cell-zone="{ row }">
            <span class="truncate block">{{ row.zone?.name || '-' }}</span>
          </template>
          <template #cell-name="{ row }">
            <span class="truncate block">{{ row.name || '-' }}</span>
          </template>
          <template #cell-type="{ row }">
            {{ row.type ? translateDeviceType(row.type) : '-' }}
          </template>
          <template #cell-status="{ row }">
            {{ row.status ? translateStatus(row.status) : 'неизвестно' }}
          </template>
          <template #cell-fw_version="{ row }">
            {{ row.fw_version || '-' }}
          </template>
          <template #cell-last_seen_at="{ row }">
            {{ row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('ru-RU') : '-' }}
          </template>
        </DataTableV2>
        <Pagination
          v-model:current-page="currentPage"
          v-model:per-page="perPage"
          :total="filtered.length"
        />
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import FilterBar from '@/Components/FilterBar.vue'
import Pagination from '@/Components/Pagination.vue'
import PageHeader from '@/Components/PageHeader.vue'
import { useDevicesStore } from '@/stores/devices'
import { useStoreEvents } from '@/composables/useStoreEvents'
import { useFavorites } from '@/composables/useFavorites'
import { useUrlState } from '@/composables/useUrlState'
import { translateDeviceType, translateStatus } from '@/utils/i18n'
import type { Device } from '@/types'
import { logger } from '@/utils/logger'
import { onWsStateChange } from '@/utils/echoClient'

const page = usePage<{ devices?: Device[] }>()
const devicesStore = useDevicesStore()
const { subscribeWithCleanup } = useStoreEvents()
let cleanupDevicesChannel: (() => void) | null = null
let devicesChannel: any = null

onMounted(() => {
  devicesStore.initFromProps(page.props)
  
  subscribeWithCleanup('device:updated', (device: Device) => {
    devicesStore.upsert(device)
  })
  
  subscribeWithCleanup('device:created', (device: Device) => {
    devicesStore.upsert(device)
  })
  
  subscribeWithCleanup('device:deleted', (deviceId: number | string) => {
    devicesStore.remove(deviceId)
  })
  
  subscribeWithCleanup('device:lifecycle:transitioned', ({ deviceId }: { deviceId: number; fromState: string; toState: string }) => {
    // Стор уже обновляется через WS, не нужно делать router.reload
    // Это предотвращает избыточные перезагрузки при флапах устройств
    devicesStore.invalidateCache()
    logger.debug('[Devices/Index] Device lifecycle transitioned, cache invalidated', { deviceId, fromState, toState })
  })
  
  // Подписка на WebSocket события обновления устройств с ресабскрайбом
      const channelName = 'hydro.devices'
      const eventName = '.device.updated'
  
  const subscribeToDevicesChannel = () => {
    // Очищаем предыдущую подписку, если есть
    if (cleanupDevicesChannel) {
      cleanupDevicesChannel()
      cleanupDevicesChannel = null
    }
    
    if (!window.Echo) {
      logger.debug('[Devices/Index] Echo not available, will retry on connection', {})
      return
    }
    
    try {
      devicesChannel = window.Echo.private(channelName)
      
      // Слушаем события обновления устройств
      // Используем broadcastAs имя 'device.updated'
      devicesChannel.listen(eventName, (event: any) => {
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
      
      cleanupDevicesChannel = () => {
        try {
          if (devicesChannel) {
            devicesChannel.stopListening(eventName)
          }
          if (typeof window.Echo?.leave === 'function') {
            window.Echo.leave(channelName)
          }
        } catch (error) {
          logger.warn('[Devices/Index] Failed to cleanup device channel', { error })
        }
        devicesChannel = null
      }
      
      logger.debug('[Devices/Index] Subscribed to hydro.devices WebSocket channel')
      
    } catch (err) {
      logger.error('[Devices/Index] Failed to subscribe to devices WebSocket:', err)
      devicesChannel = null
    }
  }
  
  // Пытаемся подписаться сразу, если Echo доступен
  subscribeToDevicesChannel()
  
  // Ресабскрайб при подключении WebSocket
  const unsubscribeWsState = onWsStateChange((state) => {
    if (state === 'connected') {
      logger.debug('[Devices/Index] WebSocket connected, resubscribing to devices channel')
      // Небольшая задержка для гарантии, что Echo полностью готов
      setTimeout(() => {
        subscribeToDevicesChannel()
      }, 100)
    }
  })
  
  // Очищаем все подписки при размонтировании компонента
  onUnmounted(() => {
    // Очищаем подписку на состояние WebSocket
    unsubscribeWsState()
    // Очищаем подписку на канал устройств
    if (cleanupDevicesChannel) {
      cleanupDevicesChannel()
      cleanupDevicesChannel = null
      devicesChannel = null
      logger.debug('[Devices/Index] Cleaned up devices channel on unmount')
    }
  })
})
const type = useUrlState<string>({
  key: 'type',
  defaultValue: '',
  parse: (value) => value ?? '',
  serialize: (value) => value || null,
})
const query = useUrlState<string>({
  key: 'query',
  defaultValue: '',
  parse: (value) => value ?? '',
  serialize: (value) => value || null,
})
const showOnlyFavorites = useUrlState<boolean>({
  key: 'favorites',
  defaultValue: false,
  parse: (value) => value === '1',
  serialize: (value) => (value ? '1' : null),
})
const currentPage = useUrlState<number>({
  key: 'page',
  defaultValue: 1,
  parse: (value) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
  },
  serialize: (value) => (value > 1 ? String(value) : null),
})
const perPage = useUrlState<number>({
  key: 'perPage',
  defaultValue: 25,
  parse: (value) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 25
  },
  serialize: (value) => (value !== 25 ? String(value) : null),
})

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

const paginatedData = computed(() => {
  if (!Array.isArray(filtered.value)) {
    return []
  }
  
  const total = filtered.value.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filtered.value.slice(start, end)
})

const columns = [
  { key: 'uid', label: 'UID', sortable: true, headerClass: 'min-w-[200px]', class: 'min-w-[200px]' },
  {
    key: 'zone',
    label: 'Зона',
    sortable: true,
    headerClass: 'min-w-[140px]',
    class: 'min-w-[140px]',
    sortAccessor: (device: Device) => device.zone?.name || '',
  },
  { key: 'name', label: 'Имя', sortable: true, headerClass: 'min-w-[140px]', class: 'min-w-[140px]' },
  { key: 'type', label: 'Тип', sortable: true, headerClass: 'min-w-[110px]', class: 'min-w-[110px]' },
  { key: 'status', label: 'Статус', sortable: true, headerClass: 'min-w-[110px]', class: 'min-w-[110px]' },
  { key: 'fw_version', label: 'Версия ПО', sortable: true, headerClass: 'min-w-[110px]', class: 'min-w-[110px]' },
  {
    key: 'last_seen_at',
    label: 'Последний раз видели',
    sortable: true,
    headerClass: 'min-w-[180px]',
    class: 'min-w-[180px]',
    sortAccessor: (device: Device) => (device.last_seen_at ? new Date(device.last_seen_at).getTime() : 0),
  },
]

// Сбрасываем на первую страницу при изменении фильтров
watch([type, query, showOnlyFavorites], () => {
  currentPage.value = 1
})

</script>
