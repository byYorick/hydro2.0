<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader
        title="Алерты"
        subtitle="Операционные предупреждения и статус подтверждения."
        eyebrow="мониторинг"
      />

      <FilterBar>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Статус:</label>
          <select v-model="statusFilter" data-testid="alerts-filter-active" class="input-select flex-1 sm:w-auto sm:min-w-[160px]">
            <option value="active">Только активные</option>
            <option value="resolved">Только решённые</option>
            <option value="all">Все</option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Зона:</label>
          <select v-model="zoneIdFilter" data-testid="alerts-filter-zone" class="input-select flex-1 sm:w-auto sm:min-w-[180px]">
            <option value="">Все зоны</option>
            <option v-for="zone in zoneOptions" :key="zone.id" :value="String(zone.id)">
              {{ zone.name }}
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Поиск:</label>
          <input
            v-model="searchQuery"
            placeholder="type / code / message"
            class="input-field flex-1 sm:w-60"
          />
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="recentOnly
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="recentOnly = !recentOnly"
          >
            24ч
          </button>
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="alarmsOnly
              ? 'border-[color:var(--accent-amber)] text-[color:var(--accent-amber)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="alarmsOnly = !alarmsOnly"
          >
            Тревоги
          </button>
        </div>

        <template #actions>
          <div v-if="selectedCount" class="text-xs text-[color:var(--text-dim)]">
            Выбрано: {{ selectedCount }}
          </div>
          <Button size="sm" variant="outline" @click="loadAlerts" :disabled="isRefreshing">
            {{ isRefreshing ? 'Обновляем...' : 'Обновить' }}
          </Button>
          <Button
            v-if="selectedCount"
            size="sm"
            variant="secondary"
            @click="bulkConfirm.open = true"
          >
            Подтвердить выбранные
          </Button>
        </template>
      </FilterBar>

      <DataTableV2
        :columns="columns"
        :rows="filteredAlerts"
        :loading="isInitialLoading"
        table-test-id="alerts-table"
        row-test-id-prefix="alert-row-"
        container-class="h-[720px]"
        :virtualize="true"
        :virtualize-threshold="100"
        :virtual-item-size="52"
        row-clickable
        @row-click="openDetails"
      >
        <template #header-select>
          <input
            type="checkbox"
            class="h-4 w-4 accent-[color:var(--accent-cyan)]"
            :checked="allVisibleSelected"
            :disabled="selectableAlerts.length === 0"
            @change="toggleSelectAll"
            @click.stop
          />
        </template>

        <template #cell-select="{ row }">
          <input
            type="checkbox"
            class="h-4 w-4 accent-[color:var(--accent-cyan)]"
            :checked="selectedIds.has(row.id)"
            :disabled="isResolved(row)"
            @change="toggleSelection(row)"
            @click.stop
          />
        </template>

        <template #cell-zone="{ row }">
          <span class="truncate block max-w-[220px]">
            {{ row.zone?.name || (row.zone_id ? `Zone #${row.zone_id}` : '-') }}
          </span>
        </template>

        <template #cell-created_at="{ row }">
          {{ formatDate(row.created_at) }}
        </template>

        <template #cell-status="{ row }">
          {{ translateStatus(row.status) }}
        </template>

        <template #row-actions="{ row }">
          <Button
            size="sm"
            variant="secondary"
            :data-testid="`alert-resolve-btn-${row.id}`"
            :disabled="isResolved(row)"
            @click.stop="openResolve(row)"
          >
            Подтвердить
          </Button>
        </template>
      </DataTableV2>
    </div>

    <ConfirmModal
      :open="confirm.open"
      title="Подтвердить алерт"
      message="Вы уверены, что алерт будет помечен как решённый?"
      :loading="confirm.loading"
      @close="closeConfirm"
      @confirm="doResolve"
    />

    <ConfirmModal
      :open="bulkConfirm.open"
      title="Подтвердить выбранные"
      message="Подтвердить выбранные алерты?"
      :loading="bulkConfirm.loading"
      @close="bulkConfirm.open = false"
      @confirm="resolveSelected"
    />

    <div v-if="selectedAlert" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-[color:var(--bg-main)] opacity-70" @click="closeDetails"></div>
      <div
        class="absolute right-0 top-0 h-full w-full max-w-md bg-[color:var(--bg-surface-strong)] border-l border-[color:var(--border-muted)] p-5 overflow-y-auto"
      >
        <div class="flex items-center justify-between mb-4">
          <div class="text-base font-semibold">Детали алерта</div>
          <Button size="sm" variant="outline" @click="closeDetails">Закрыть</Button>
        </div>
        <div class="space-y-4 text-sm text-[color:var(--text-muted)]">
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Тип</div>
            <div class="text-[color:var(--text-primary)] font-semibold">{{ selectedAlert.type }}</div>
          </div>
          <div v-if="selectedAlert.code" class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Code</div>
            <div class="text-[color:var(--text-primary)] font-semibold">{{ selectedAlert.code }}</div>
          </div>
          <div v-if="selectedAlert.source" class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Source</div>
            <div class="text-[color:var(--text-primary)] font-semibold">{{ selectedAlert.source }}</div>
          </div>
          <div v-if="selectedAlert.message" class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Сообщение</div>
            <div class="text-[color:var(--text-primary)]">{{ selectedAlert.message }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Статус</div>
            <div class="text-[color:var(--text-primary)]">{{ translateStatus(selectedAlert.status) }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Создан</div>
            <div class="text-[color:var(--text-primary)]">{{ formatDate(selectedAlert.created_at) }}</div>
          </div>
          <div v-if="selectedAlert.resolved_at" class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Подтвержден</div>
            <div class="text-[color:var(--text-primary)]">{{ formatDate(selectedAlert.resolved_at) }}</div>
          </div>
          <div class="space-y-1" v-if="selectedAlert.zone_id">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Зона</div>
            <Link
              class="text-[color:var(--accent-cyan)] font-semibold hover:underline"
              :href="`/zones/${selectedAlert.zone_id}`"
            >
              {{ selectedAlert.zone?.name || `Zone #${selectedAlert.zone_id}` }}
            </Link>
          </div>
          <div v-if="detailsJson" class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Details</div>
            <pre class="text-xs whitespace-pre-wrap rounded-lg border border-[color:var(--border-muted)] p-3 bg-[color:var(--bg-surface)]">
{{ detailsJson }}
            </pre>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import FilterBar from '@/Components/FilterBar.vue'
import PageHeader from '@/Components/PageHeader.vue'
import { subscribeAlerts } from '@/ws/subscriptions'
import { translateStatus } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useUrlState } from '@/composables/useUrlState'
import { useAlertsStore } from '@/stores/alerts'
import type { Alert } from '@/types/Alert'

interface AlertRecord extends Omit<Alert, 'zone'> {
  details?: any
  code?: string
  source?: string
  message?: string
  zone?: { id: number; name: string } | undefined
}

interface PageProps {
  alerts?: AlertRecord[]
  [key: string]: any
}

const page = usePage<PageProps>()
const alertsStore = useAlertsStore()
const { api } = useApi()

const statusFilter = useUrlState<'active' | 'resolved' | 'all'>({
  key: 'status',
  defaultValue: 'active',
  parse: (value) => {
    if (value === 'resolved') return 'resolved'
    if (value === 'all') return 'all'
    return 'active'
  },
  serialize: (value) => value,
})

const zoneIdFilter = useUrlState<string>({
  key: 'zone_id',
  defaultValue: '',
  parse: (value) => {
    if (!value) return ''
    return /^\d+$/.test(value) ? value : ''
  },
  serialize: (value) => value || null,
})

const searchQuery = useUrlState<string>({
  key: 'search',
  defaultValue: '',
  parse: (value) => value ?? '',
  serialize: (value) => value || null,
})

const recentOnly = useUrlState<boolean>({
  key: 'recent',
  defaultValue: false,
  parse: (value) => value === '1',
  serialize: (value) => (value ? '1' : null),
})

const alarmsOnly = useUrlState<boolean>({
  key: 'alarms',
  defaultValue: false,
  parse: (value) => value === '1',
  serialize: (value) => (value ? '1' : null),
})

const initialAlerts = Array.isArray(page.props.alerts) ? page.props.alerts : []
alertsStore.setAll(initialAlerts as Alert[])

watch(
  () => page.props.alerts,
  (newAlerts) => {
    if (Array.isArray(newAlerts)) {
      alertsStore.setAll(newAlerts as Alert[])
    }
  },
  { deep: true }
)

const alerts = computed(() => alertsStore.items as AlertRecord[])

const isRefreshing = ref(false)
const isInitialLoading = computed(() => isRefreshing.value && alerts.value.length === 0)

const loadAlerts = async (): Promise<void> => {
  if (isRefreshing.value) return
  isRefreshing.value = true

  try {
    const params: Record<string, string | number> = {}
    if (statusFilter.value !== 'all') {
      params.status = statusFilter.value
    }
    if (zoneIdFilter.value) {
      params.zone_id = parseInt(zoneIdFilter.value)
    }

    const response = await api.get('/api/alerts', { params })
    const payload = response?.data?.data
    const list = Array.isArray(payload?.data)
      ? payload.data
      : Array.isArray(payload)
        ? payload
        : []
    alertsStore.setAll(list)
  } catch (err) {
    logger.error('[Alerts] Failed to load alerts', err)
  } finally {
    isRefreshing.value = false
  }
}

watch([statusFilter, zoneIdFilter], () => {
  loadAlerts()
}, { immediate: true })

const zoneOptions = computed(() => {
  const map = new Map<number, string>()
  alerts.value.forEach((alert) => {
    const zone = alert.zone
    if (zone?.id) {
      map.set(zone.id, zone.name || `Zone #${zone.id}`)
    }
  })
  return Array.from(map.entries()).map(([id, name]) => ({ id, name }))
})

const searchNeedle = computed(() => searchQuery.value.trim().toLowerCase())

const isResolved = (alert: AlertRecord): boolean => {
  return alert.status === 'resolved' || alert.status === 'RESOLVED'
}

const isAlarm = (alert: AlertRecord): boolean => {
  const type = (alert.type || '').toUpperCase()
  const code = (alert.code || '').toUpperCase()
  const severity = String(alert.details?.severity || alert.details?.level || '').toUpperCase()
  return type.includes('ALARM') || type.includes('ALERT') || code.includes('ALARM') || severity.includes('CRITICAL')
}

const filteredAlerts = computed(() => {
  const needle = searchNeedle.value
  const now = Date.now()
  const dayMs = 24 * 60 * 60 * 1000

  return alerts.value.filter((alert) => {
    if (statusFilter.value !== 'all') {
      const resolved = isResolved(alert)
      if (statusFilter.value === 'active' && resolved) return false
      if (statusFilter.value === 'resolved' && !resolved) return false
    }

    if (zoneIdFilter.value) {
      if (String(alert.zone_id || '') !== zoneIdFilter.value) return false
    }

    if (recentOnly.value && alert.created_at) {
      const created = new Date(alert.created_at).getTime()
      if (Number.isNaN(created) || now - created > dayMs) return false
    }

    if (alarmsOnly.value && !isAlarm(alert)) return false

    if (needle) {
      const detailsText = alert.details ? JSON.stringify(alert.details) : ''
      const searchStack = [
        alert.type,
        alert.code,
        alert.message,
        alert.source,
        detailsText,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      if (!searchStack.includes(needle)) return false
    }

    return true
  })
})

const selectableAlerts = computed(() => filteredAlerts.value.filter((alert) => !isResolved(alert)))
const selectedIds = ref<Set<number>>(new Set())

const selectedCount = computed(() => selectedIds.value.size)

const allVisibleSelected = computed(() => {
  if (selectableAlerts.value.length === 0) return false
  return selectableAlerts.value.every((alert) => selectedIds.value.has(alert.id))
})

const toggleSelection = (alert: AlertRecord): void => {
  if (isResolved(alert)) return
  const next = new Set(selectedIds.value)
  if (next.has(alert.id)) {
    next.delete(alert.id)
  } else {
    next.add(alert.id)
  }
  selectedIds.value = next
}

const toggleSelectAll = (): void => {
  if (allVisibleSelected.value) {
    selectedIds.value = new Set()
    return
  }
  const next = new Set<number>()
  selectableAlerts.value.forEach((alert) => next.add(alert.id))
  selectedIds.value = next
}

watch(filteredAlerts, () => {
  const next = new Set<number>()
  filteredAlerts.value.forEach((alert) => {
    if (selectedIds.value.has(alert.id) && !isResolved(alert)) {
      next.add(alert.id)
    }
  })
  selectedIds.value = next
})

const columns = [
  { key: 'select', label: '', sortable: false, headerClass: 'w-10' },
  { key: 'type', label: 'Тип', sortable: true },
  {
    key: 'zone',
    label: 'Зона',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => alert.zone?.name || `Zone #${alert.zone_id}`,
  },
  {
    key: 'created_at',
    label: 'Время',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => new Date(alert.created_at).getTime(),
  },
  { key: 'status', label: 'Статус', sortable: true },
]

const confirm = ref({ open: false, alertId: null as number | null, loading: false })
const bulkConfirm = ref({ open: false, loading: false })

const openResolve = (alert: AlertRecord): void => {
  confirm.value = { open: true, alertId: alert.id, loading: false }
}

const closeConfirm = (): void => {
  confirm.value = { open: false, alertId: null, loading: false }
}

const applyResolved = (id: number, updated?: AlertRecord): void => {
  if (updated) {
    alertsStore.upsert(updated as Alert)
  } else {
    alertsStore.setResolved(id)
  }
}

const doResolve = async (): Promise<void> => {
  if (!confirm.value.alertId) return
  confirm.value.loading = true

  try {
    const response = await api.patch(`/api/alerts/${confirm.value.alertId}/ack`, {})
    const updated = (response?.data as { data?: AlertRecord })?.data
    applyResolved(confirm.value.alertId, updated)
  } catch (err) {
    logger.error('[Alerts] Failed to resolve alert', err)
  } finally {
    closeConfirm()
  }
}

const resolveSelected = async (): Promise<void> => {
  const ids = Array.from(selectedIds.value)
  if (!ids.length) {
    bulkConfirm.value.open = false
    return
  }

  bulkConfirm.value.loading = true
  try {
    await Promise.all(ids.map(async (id) => {
      const response = await api.patch(`/api/alerts/${id}/ack`, {})
      const updated = (response?.data as { data?: AlertRecord })?.data
      applyResolved(id, updated)
    }))
  } catch (err) {
    logger.error('[Alerts] Failed to resolve alerts', err)
  } finally {
    bulkConfirm.value = { open: false, loading: false }
    selectedIds.value = new Set()
  }
}

const selectedAlertId = ref<number | null>(null)

const selectedAlert = computed<AlertRecord | null>(() => {
  if (!selectedAlertId.value) return null
  return (alertsStore.alertById(selectedAlertId.value) as AlertRecord) || null
})

const detailsJson = computed(() => {
  if (!selectedAlert.value?.details) return ''
  try {
    return JSON.stringify(selectedAlert.value.details, null, 2)
  } catch {
    return String(selectedAlert.value.details)
  }
})

const openDetails = (alert: AlertRecord): void => {
  selectedAlertId.value = alert.id
}

const closeDetails = (): void => {
  selectedAlertId.value = null
}

const formatDate = (value?: string): string => {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ru-RU')
}

let unsubscribeAlerts: (() => void) | null = null

onMounted(() => {
  unsubscribeAlerts = subscribeAlerts((event) => {
    const payload = event as AlertRecord
    if (payload?.id) {
      alertsStore.upsert(payload as Alert)
    }
  })
})

onUnmounted(() => {
  unsubscribeAlerts?.()
  unsubscribeAlerts = null
})
</script>
