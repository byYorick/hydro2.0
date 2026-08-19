<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader
        title="Узлы"
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
              Всего узлов
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

      <section
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/30 p-4 space-y-3"
        data-testid="site-weather-stations-panel"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
              Общие метеостанции
            </h3>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Независимые устройства площадки. Теплицы подключают их телеметрию в настройках климата.
            </p>
          </div>
          <div
            v-if="canConfigureDevices"
            class="flex flex-wrap items-center gap-2"
          >
            <select
              v-model="assignWeatherNodeId"
              class="input-select min-w-[180px]"
              data-testid="site-weather-assign-select"
            >
              <option :value="null">
                Выберите climate-ноду
              </option>
              <option
                v-for="node in assignableWeatherCandidates"
                :key="node.id"
                :value="node.id"
              >
                {{ node.name || node.uid }} ({{ node.uid }})
              </option>
            </select>
            <Button
              size="sm"
              variant="outline"
              :disabled="!assignWeatherNodeId || weatherStationBusy"
              data-testid="site-weather-assign-button"
              @click="assignSelectedWeatherStation"
            >
              Назначить
            </Button>
          </div>
        </div>
        <ul
          v-if="siteWeatherStations.length"
          class="space-y-2"
        >
          <li
            v-for="station in siteWeatherStations"
            :key="station.id"
            class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-3 py-2 text-sm"
          >
            <div class="min-w-0">
              <div class="font-medium text-[color:var(--text-primary)] truncate">
                {{ station.name || station.uid }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)]">
                {{ station.uid }} · {{ station.status || 'unknown' }}
              </div>
            </div>
            <Button
              v-if="canConfigureDevices"
              size="sm"
              variant="ghost"
              :disabled="weatherStationBusy"
              @click="unassignWeatherStation(station.id)"
            >
              Снять
            </Button>
          </li>
        </ul>
        <p
          v-else
          class="text-xs text-[color:var(--text-dim)]"
        >
          Метеостанции ещё не назначены.
        </p>
      </section>

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
            <option
              v-for="option in typeOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
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
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <button
            class="h-9 px-3 rounded-md border text-sm transition-colors flex items-center gap-1.5 bg-[color:var(--bg-elevated)]"
            :class="showOnlyProblematic
              ? 'border-[color:var(--badge-danger-border)] text-[color:var(--accent-red)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
            data-testid="devices-filter-problematic"
            @click="showOnlyProblematic = !showOnlyProblematic"
          >
            <span>Только проблемные</span>
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
            {{ formatDeviceLastSeen(row.last_seen_at) }}
          </template>
          <template #cell-rssi="{ row }">
            {{ formatDeviceRssi(row.rssi) }}
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
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
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
import { useRole } from '@/composables/useRole'
import { useUrlState } from '@/composables/useUrlState'
import { api } from '@/services/api'
import type { SiteWeatherStation } from '@/services/api/siteWeatherStations'
import { translateDeviceType, translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import type { Device } from '@/types'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'

const page = usePage<{ devices?: Device[] }>()
const { showToast } = useToast()
const { canConfigureDevices, canSubscribeUnassignedDevices } = useRole()
const devicesStore = useDevicesStore()
const { subscribeWithCleanup } = useStoreEvents()
const deviceUpdateEventName = '.device.updated'
const zoneChannels = new Map<number, () => void>()
let stopUnassignedChannel: (() => void) | null = null

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

  const channelName = `hydro.zones.${zoneId}`
  try {
    const stopSubscription = subscribeManagedChannelEvents({
      channelName,
      componentTag: `Devices/Index:${zoneId}`,
      leaveOnCleanup: true,
      eventHandlers: {
        [deviceUpdateEventName]: (payload) => {
          handleDeviceUpdate(payload)
        },
      },
    })
    zoneChannels.set(zoneId, stopSubscription)
    logger.debug('[Devices/Index] Subscribed to zone device channel', { channel: channelName })
  } catch (err) {
    logger.error('[Devices/Index] Failed to subscribe to zone device channel', { zoneId, err })
    showToast(`Ошибка подписки на WebSocket зоны #${zoneId}`, 'error', TOAST_TIMEOUT.NORMAL)
  }
}

const unsubscribeZoneChannel = (zoneId: number): void => {
  const stopSubscription = zoneChannels.get(zoneId)
  if (!stopSubscription) {
    return
  }

  try {
    stopSubscription()
  } catch (error) {
    logger.warn('[Devices/Index] Failed to cleanup zone channel', { zoneId, error })
  }

  zoneChannels.delete(zoneId)
}

const subscribeUnassignedChannel = (): void => {
  if (stopUnassignedChannel) {
    return
  }

  try {
    stopUnassignedChannel = subscribeManagedChannelEvents({
      channelName: 'hydro.devices',
      componentTag: 'Devices/Index:unassigned',
      leaveOnCleanup: true,
      eventHandlers: {
        [deviceUpdateEventName]: (payload) => {
          handleDeviceUpdate(payload)
        },
      },
    })
    logger.debug('[Devices/Index] Subscribed to unassigned devices channel')
  } catch (err) {
    logger.error('[Devices/Index] Failed to subscribe to unassigned devices channel', err)
    showToast('Ошибка подписки на канал неназначенных устройств', 'error', TOAST_TIMEOUT.NORMAL)
    stopUnassignedChannel = null
  }
}

const unsubscribeUnassignedChannel = (): void => {
  if (!stopUnassignedChannel) {
    return
  }

  try {
    stopUnassignedChannel()
  } catch (error) {
    logger.warn('[Devices/Index] Failed to cleanup unassigned channel', { error })
  }

  stopUnassignedChannel = null
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

  if (canSubscribeUnassignedDevices.value) {
    subscribeUnassignedChannel()
  } else {
    unsubscribeUnassignedChannel()
  }
}

const resetDeviceChannels = (): void => {
  Array.from(zoneChannels.keys()).forEach(zoneId => unsubscribeZoneChannel(zoneId))
  unsubscribeUnassignedChannel()
}

onMounted(() => {
  devicesStore.initFromProps(page.props)
  void loadSiteWeatherStations()
  
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

  onUnmounted(() => {
    stopChannelWatcher()
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
const showOnlyProblematic = useUrlState<boolean>({
  key: 'problems',
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

const siteWeatherStations = ref<SiteWeatherStation[]>([])
const assignWeatherNodeId = ref<number | null>(null)
const weatherStationBusy = ref(false)

const siteWeatherStationIds = computed(() => new Set(siteWeatherStations.value.map((s) => s.id)))

const assignableWeatherCandidates = computed(() => {
  return allDevices.value.filter((device) => {
    if (String(device.type ?? '').toLowerCase() !== 'climate') {
      return false
    }
    if (siteWeatherStationIds.value.has(device.id)) {
      return false
    }
    return device.zone_id == null && (device as Device & { zone?: { id?: number } }).zone?.id == null
  })
})

async function loadSiteWeatherStations(): Promise<void> {
  try {
    const stations = await api.siteWeatherStations.list()
    siteWeatherStations.value = Array.isArray(stations) ? stations : []
  } catch {
    siteWeatherStations.value = []
  }
}

async function assignSelectedWeatherStation(): Promise<void> {
  if (!assignWeatherNodeId.value || weatherStationBusy.value) {
    return
  }
  weatherStationBusy.value = true
  try {
    await api.siteWeatherStations.assign(assignWeatherNodeId.value)
    assignWeatherNodeId.value = null
    await loadSiteWeatherStations()
    showToast('Метеостанция назначена.', 'success', TOAST_TIMEOUT.NORMAL)
  } catch {
    showToast('Не удалось назначить метеостанцию.', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    weatherStationBusy.value = false
  }
}

async function unassignWeatherStation(nodeId: number): Promise<void> {
  if (weatherStationBusy.value) {
    return
  }
  weatherStationBusy.value = true
  try {
    await api.siteWeatherStations.unassign(nodeId)
    await loadSiteWeatherStations()
    showToast('Метеостанция снята.', 'success', TOAST_TIMEOUT.NORMAL)
  } catch {
    showToast('Не удалось снять метеостанцию.', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    weatherStationBusy.value = false
  }
}

function isDeviceOffline(device: Device): boolean {
  const status = String(device.status || '').toLowerCase()
  return status === 'offline' || status === 'error' || status === 'stale'
}

function isDeviceProblematic(device: Device): boolean {
  return isDeviceOffline(device) || device.status === 'degraded'
}

function formatDeviceLastSeen(value?: string | null): string {
  if (!value) return '-'
  return formatTime(value) || '-'
}

function formatDeviceRssi(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  return `${value} dBm`
}

const typeOptions = computed(() => {
  const unique = Array.from(new Set(
    allDevices.value
      .map((device) => String(device.type || '').trim())
      .filter((type) => type.length > 0),
  )).sort((a, b) => a.localeCompare(b, 'ru'))

  return unique.map((value) => ({
    value,
    label: translateDeviceType(value),
  }))
})
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
  
  const matched = devices.filter(d => {
    const okType = typeFilter ? d.type === typeFilter : true
    const okQuery = queryFilter ? (d.uid || d.name || '').toLowerCase().includes(queryFilter) : true
    const okFavorites = showOnlyFavorites.value ? isDeviceFavorite(d.id) : true
    const okProblematic = showOnlyProblematic.value ? isDeviceProblematic(d) : true
    return okType && okQuery && okFavorites && okProblematic
  })

  return matched.slice().sort((a, b) => {
    const aOffline = isDeviceOffline(a) ? 0 : 1
    const bOffline = isDeviceOffline(b) ? 0 : 1
    if (aOffline !== bOffline) return aOffline - bOffline
    const aSeen = a.last_seen_at ? new Date(a.last_seen_at).getTime() : 0
    const bSeen = b.last_seen_at ? new Date(b.last_seen_at).getTime() : 0
    return bSeen - aSeen
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
    label: 'Последняя связь',
    sortable: true,
    headerClass: 'min-w-[160px]',
    class: 'min-w-[160px]',
    sortAccessor: (device: Device) => (device.last_seen_at ? new Date(device.last_seen_at).getTime() : 0),
  },
  {
    key: 'rssi',
    label: 'RSSI',
    sortable: true,
    headerClass: 'min-w-[90px]',
    class: 'min-w-[90px]',
    sortAccessor: (device: Device) => (typeof device.rssi === 'number' ? device.rssi : -999),
  },
]

// Сбрасываем на первую страницу при изменении фильтров
watch([type, query, showOnlyFavorites, showOnlyProblematic], () => {
  currentPage.value = 1
})

</script>
