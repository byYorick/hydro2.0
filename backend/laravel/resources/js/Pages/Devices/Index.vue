<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader
        title="Устройства"
        subtitle="Список узлов, статусы и быстрые действия."
        eyebrow="инфраструктура"
      >
        <template #actions>
          <Link
            v-if="canConfigureDevices"
            href="/devices/add"
          >
            <Button
              size="sm"
              variant="primary"
            >
              <svg
                class="w-4 h-4 mr-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Добавить ноду
            </Button>
          </Link>
        </template>
        <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-4">
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Всего устройств
            </div>
            <div class="ui-kpi-value">
              {{ totalDevices }}
            </div>
            <div class="ui-kpi-hint">
              Узлы в реестре
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Онлайн
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-green)]">
              {{ onlineDevices }}
            </div>
            <div class="ui-kpi-hint">
              Доступны сейчас
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Оффлайн
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-amber)]">
              {{ offlineDevices }}
            </div>
            <div class="ui-kpi-hint">
              Требуют проверки
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              По фильтру
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
              {{ visibleDevices }}
            </div>
            <div class="ui-kpi-hint">
              Отображается в таблице
            </div>
          </div>
        </div>
      </PageHeader>

      <FilterBar>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Тип:</label>
          <select
            v-model="type"
            class="input-select flex-1 sm:w-auto sm:min-w-[140px]"
            data-testid="devices-filter-type"
          >
            <option value="">
              Все
            </option>
            <option value="sensor">
              Датчик
            </option>
            <option value="actuator">
              Актуатор
            </option>
            <option value="controller">
              Контроллер
            </option>
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
            class="h-9 px-3 rounded-md border text-sm transition-colors flex items-center gap-1.5 bg-[color:var(--bg-elevated)]"
            :class="showOnlyFavorites
              ? 'border-[color:var(--badge-warning-border)] text-[color:var(--accent-amber)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
            data-testid="devices-filter-favorites"
            @click="showOnlyFavorites = !showOnlyFavorites"
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
                class="p-0.5 rounded hover:bg-[color:var(--bg-surface-strong)] transition-colors shrink-0 w-5 h-5 flex items-center justify-center"
                :title="isDeviceFavorite(row.id) ? 'Удалить из избранного' : 'Добавить в избранное'"
                @click.stop="toggleDeviceFavorite(row.id)"
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
              <Link
                :href="`/devices/${row.uid || row.id}`"
                class="text-[color:var(--accent-cyan)] hover:underline truncate min-w-0"
              >
                {{ row.uid || row.id }}
              </Link>
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
import { useToast } from '@/composables/useToast'
import { useUrlState } from '@/composables/useUrlState'
import { translateDeviceType, translateStatus } from '@/utils/i18n'
import type { Device } from '@/types'
import { logger } from '@/utils/logger'
import { onWsStateChange } from '@/utils/echoClient'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

const page = usePage<{ devices?: Device[] }>()
const { showToast } = useToast()
const canConfigureDevices = computed(() => {
  const role = (page.props as any)?.auth?.user?.role ?? 'viewer'
  return role === 'agronomist' || role === 'admin'
})
const devicesStore = useDevicesStore()
const { subscribeWithCleanup } = useStoreEvents()
const deviceUpdateEventName = '.device.updated'
const zoneChannels = new Map<number, any>()
let unassignedChannel: any = null

const zoneIds = computed(() => {
  const ids = new Set<number>()
  devicesStore.allDevices.forEach(device => {
    const zoneId = device.zone?.id ?? device.zone_id ?? null
    if (zoneId) {
      ids.add(zoneId)
    }
  })
  return Array.from(ids)
})

const handleDeviceUpdate = (event: any): void => {
  logger.debug('[Devices/Index] Received device update via WebSocket', event)

  if (event.device) {
    const device = event.device as Device
    devicesStore.upsert(device)

    if (event.device.was_recently_created) {
      logger.info('[Devices/Index] New device created:', device.uid)
    }
  }
}

const subscribeZoneChannel = (zoneId: number): void => {
  if (zoneChannels.has(zoneId)) {
    return
  }

  if (!window.Echo) {
    logger.debug('[Devices/Index] Echo not available, will retry on connection', { zoneId })
    return
  }

  const channelName = `hydro.zones.${zoneId}`
  try {
    const channel = window.Echo.private(channelName)
    channel.listen(deviceUpdateEventName, handleDeviceUpdate)
    zoneChannels.set(zoneId, channel)
    logger.debug('[Devices/Index] Subscribed to zone device channel', { channel: channelName })
  } catch (err) {
    logger.error('[Devices/Index] Failed to subscribe to zone device channel', { zoneId, err })
    showToast(`Ошибка подписки на WebSocket зоны #${zoneId}`, 'error', TOAST_TIMEOUT.NORMAL)
  }
}

const unsubscribeZoneChannel = (zoneId: number): void => {
  const channel = zoneChannels.get(zoneId)
  if (!channel) {
    return
  }

  const channelName = `hydro.zones.${zoneId}`
  try {
    channel.stopListening(deviceUpdateEventName)
    if (typeof window.Echo?.leave === 'function') {
      window.Echo.leave(channelName)
    }
  } catch (error) {
    logger.warn('[Devices/Index] Failed to cleanup zone channel', { zoneId, error })
  }

  zoneChannels.delete(zoneId)
}

const subscribeUnassignedChannel = (): void => {
  if (unassignedChannel) {
    return
  }

  if (!window.Echo) {
    logger.debug('[Devices/Index] Echo not available for unassigned channel', {})
    return
  }

  try {
    unassignedChannel = window.Echo.private('hydro.devices')
    unassignedChannel.listen(deviceUpdateEventName, handleDeviceUpdate)
    logger.debug('[Devices/Index] Subscribed to unassigned devices channel')
  } catch (err) {
    logger.error('[Devices/Index] Failed to subscribe to unassigned devices channel', err)
    showToast('Ошибка подписки на канал неназначенных устройств', 'error', TOAST_TIMEOUT.NORMAL)
    unassignedChannel = null
  }
}

const unsubscribeUnassignedChannel = (): void => {
  if (!unassignedChannel) {
    return
  }

  try {
    unassignedChannel.stopListening(deviceUpdateEventName)
    if (typeof window.Echo?.leave === 'function') {
      window.Echo.leave('hydro.devices')
    }
  } catch (error) {
    logger.warn('[Devices/Index] Failed to cleanup unassigned channel', { error })
  }

  unassignedChannel = null
}

const syncDeviceChannels = (): void => {
  const targetZoneIds = new Set(zoneIds.value)

  Array.from(zoneChannels.keys()).forEach(zoneId => {
    if (!targetZoneIds.has(zoneId)) {
      unsubscribeZoneChannel(zoneId)
    }
  })

  targetZoneIds.forEach(zoneId => {
    if (!zoneChannels.has(zoneId)) {
      subscribeZoneChannel(zoneId)
    }
  })
  subscribeUnassignedChannel()
}

const resetDeviceChannels = (): void => {
  Array.from(zoneChannels.keys()).forEach(zoneId => unsubscribeZoneChannel(zoneId))
  unsubscribeUnassignedChannel()
}

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
  
  subscribeWithCleanup('device:lifecycle:transitioned', ({ deviceId, fromState, toState }: { deviceId: number; fromState: string; toState: string }) => {
    // Стор уже обновляется через WS, не нужно делать router.reload
    // Это предотвращает избыточные перезагрузки при флапах устройств
    devicesStore.invalidateCache()
    logger.debug('[Devices/Index] Device lifecycle transitioned, cache invalidated', { deviceId, fromState, toState })
  })
  
  const stopChannelWatcher = watch(zoneIds, () => {
    syncDeviceChannels()
  }, { immediate: true })

  const unsubscribeWsState = onWsStateChange((state) => {
    if (state === 'connected') {
      logger.debug('[Devices/Index] WebSocket connected, resubscribing device channels')
      setTimeout(() => {
        resetDeviceChannels()
        syncDeviceChannels()
      }, 100)
    } else if (state === 'disconnected') {
      resetDeviceChannels()
    }
  })

  onUnmounted(() => {
    stopChannelWatcher()
    unsubscribeWsState()
    resetDeviceChannels()
    logger.debug('[Devices/Index] Cleaned up device channels on unmount')
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
const allDevices = computed(() => (Array.isArray(devicesStore.allDevices) ? devicesStore.allDevices : []))
const totalDevices = computed(() => allDevices.value.length)
const onlineDevices = computed(() => allDevices.value.filter((device) => device.status === 'online').length)
const offlineDevices = computed(() => allDevices.value.filter((device) => device.status === 'offline').length)

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
const visibleDevices = computed(() => filtered.value.length)

const paginatedData = computed(() => {
  if (!Array.isArray(filtered.value)) {
    return []
  }
  
  const total = filtered.value.length
  if (total === 0) return []
  
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filtered.value.slice(start, end)
})

watch([filtered, perPage], () => {
  const total = filtered.value.length
  if (total === 0) {
    currentPage.value = 1
    return
  }
  const maxPage = Math.ceil(total / perPage.value) || 1
  if (currentPage.value > maxPage) {
    currentPage.value = maxPage
  }
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
