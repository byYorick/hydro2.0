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
          <select
            v-model="statusFilter"
            data-testid="alerts-filter-active"
            class="input-select flex-1 sm:w-auto sm:min-w-[160px]"
          >
            <option value="active">
              Только активные
            </option>
            <option value="resolved">
              Только решённые
            </option>
            <option value="all">
              Все
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Зона:</label>
          <select
            v-model="zoneIdFilter"
            data-testid="alerts-filter-zone"
            class="input-select flex-1 sm:w-auto sm:min-w-[180px]"
          >
            <option value="">
              Все зоны
            </option>
            <option
              v-for="zone in zoneOptions"
              :key="zone.id"
              :value="String(zone.id)"
            >
              {{ zone.name }}
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Source:</label>
          <select
            v-model="sourceFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[150px]"
          >
            <option value="">
              Все
            </option>
            <option value="biz">
              biz
            </option>
            <option value="infra">
              infra
            </option>
            <option value="node">
              node
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Severity:</label>
          <select
            v-model="severityFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[150px]"
          >
            <option value="">
              Все
            </option>
            <option value="critical">
              critical
            </option>
            <option value="error">
              error
            </option>
            <option value="warning">
              warning
            </option>
            <option value="info">
              info
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Category:</label>
          <select
            v-model="categoryFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[170px]"
          >
            <option value="">
              Все
            </option>
            <option value="agronomy">
              agronomy
            </option>
            <option value="operations">
              operations
            </option>
            <option value="infrastructure">
              infrastructure
            </option>
            <option value="node">
              node
            </option>
            <option value="safety">
              safety
            </option>
            <option value="config">
              config
            </option>
            <option value="other">
              other
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

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Подавление:</label>
          <input
            v-model.number="toastSuppressionSec"
            type="number"
            min="0"
            max="600"
            step="5"
            class="input-field w-24"
          />
          <span class="text-xs text-[color:var(--text-dim)]">сек</span>
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
          <div
            v-if="selectedCount"
            class="text-xs text-[color:var(--text-dim)]"
          >
            Выбрано: {{ selectedCount }}
          </div>
          <Button
            size="sm"
            variant="outline"
            :disabled="isRefreshing"
            @click="loadAlerts"
          >
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

        <template #cell-type="{ row }">
          <span class="truncate block max-w-[320px]">
            {{ getAlertMeta(row).title }}
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

    <div
      v-if="selectedAlert"
      class="fixed inset-0 z-50"
    >
      <div
        class="absolute inset-0 bg-[color:var(--bg-main)] opacity-70"
        @click="closeDetails"
      ></div>
      <div
        class="absolute right-0 top-0 h-full w-full max-w-md bg-[color:var(--bg-surface-strong)] border-l border-[color:var(--border-muted)] p-5 overflow-y-auto"
      >
        <div class="flex items-center justify-between mb-4">
          <div class="text-base font-semibold">
            Детали алерта
          </div>
          <Button
            size="sm"
            variant="outline"
            @click="closeDetails"
          >
            Закрыть
          </Button>
        </div>
        <div class="space-y-4 text-sm text-[color:var(--text-muted)]">
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Тип
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ getAlertMeta(selectedAlert).title }}
            </div>
          </div>
          <div
            v-if="selectedAlert.code"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Code
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ selectedAlert.code }}
            </div>
          </div>
          <div
            v-if="selectedAlert.source"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Source
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ selectedAlert.source }}
            </div>
          </div>
          <div
            v-if="selectedAlertMessage"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Сообщение
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ selectedAlertMessage }}
            </div>
          </div>
          <div
            v-if="getAlertMeta(selectedAlert).recommendation"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Рекомендация
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ getAlertMeta(selectedAlert).recommendation }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Статус
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ translateStatus(selectedAlert.status) }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Создан
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ formatDate(selectedAlert.created_at) }}
            </div>
          </div>
          <div
            v-if="selectedAlert.resolved_at"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Подтвержден
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ formatDate(selectedAlert.resolved_at) }}
            </div>
          </div>
          <div
            v-if="selectedAlert.zone_id"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Зона
            </div>
            <Link
              class="text-[color:var(--accent-cyan)] font-semibold hover:underline"
              :href="`/zones/${selectedAlert.zone_id}`"
            >
              {{ selectedAlert.zone?.name || `Zone #${selectedAlert.zone_id}` }}
            </Link>
          </div>
          <div
            v-if="detailsJson"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Details
            </div>
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
import { useToast } from '@/composables/useToast'
import { useUrlState } from '@/composables/useUrlState'
import { useAlertsStore } from '@/stores/alerts'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { resolveAlertCodeMeta, resolveAlertSeverity, type AlertSeverity, type AlertCodeMeta } from '@/constants/alertErrorMap'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
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

interface AlertCatalogItem {
  code: string
  title: string
  description: string
  recommendation?: string
  severity?: AlertSeverity
}

const page = usePage<PageProps>()
const alertsStore = useAlertsStore()
const { api } = useApi()
const { showToast } = useToast()
const ALERT_TOAST_SUPPRESSION_KEY = 'hydro.alerts.toastSuppressionSec'
const toastSuppressionSec = ref(30)
const isSyncingSuppressionPreference = ref(false)
let skipSuppressionPersistCount = 0
const recentAlertToastAt = new Map<string, number>()
const toastSuppressionMs = computed(() => Math.max(0, Math.floor(Number(toastSuppressionSec.value) || 0) * 1000))
let suppressionPersistTimer: ReturnType<typeof setTimeout> | null = null

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

const sourceFilter = useUrlState<string>({
  key: 'source',
  defaultValue: '',
  parse: (value) => {
    const normalized = String(value || '').toLowerCase()
    return ['biz', 'infra', 'node'].includes(normalized) ? normalized : ''
  },
  serialize: (value) => value || null,
})

const severityFilter = useUrlState<string>({
  key: 'severity',
  defaultValue: '',
  parse: (value) => {
    const normalized = String(value || '').toLowerCase()
    return ['critical', 'error', 'warning', 'info'].includes(normalized) ? normalized : ''
  },
  serialize: (value) => value || null,
})

const categoryFilter = useUrlState<string>({
  key: 'category',
  defaultValue: '',
  parse: (value) => {
    const normalized = String(value || '').toLowerCase()
    return ['agronomy', 'operations', 'infrastructure', 'node', 'safety', 'config', 'other'].includes(normalized)
      ? normalized
      : ''
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
const catalogMetaByCode = ref<Record<string, AlertCodeMeta>>({})

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
    if (sourceFilter.value) {
      params.source = sourceFilter.value
    }
    if (severityFilter.value) {
      params.severity = severityFilter.value
    }
    if (categoryFilter.value) {
      params.category = categoryFilter.value
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
    if (!(err as any)?.response) {
      showToast(`Не удалось загрузить алерты: ${extractHumanErrorMessage(err, 'Ошибка загрузки')}`, 'error', TOAST_TIMEOUT.NORMAL)
    }
  } finally {
    isRefreshing.value = false
  }
}

watch([statusFilter, zoneIdFilter], () => {
  loadAlerts()
}, { immediate: true })

watch([sourceFilter, severityFilter, categoryFilter], () => {
  loadAlerts()
})

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

const getAlertMeta = (alert?: AlertRecord | null): AlertCodeMeta => {
  const code = String(alert?.code || '').trim().toLowerCase()
  if (code && catalogMetaByCode.value[code]) {
    return catalogMetaByCode.value[code]
  }
  return resolveAlertCodeMeta(alert?.code)
}

const getAlertMessage = (alert?: AlertRecord | null): string => {
  if (!alert) return ''
  const messageFromPayload = String(alert.message || alert.details?.message || '').trim()
  if (messageFromPayload) return messageFromPayload
  return getAlertMeta(alert).description
}

const isResolved = (alert: AlertRecord): boolean => {
  return alert.status === 'resolved' || alert.status === 'RESOLVED'
}

const isAlarm = (alert: AlertRecord): boolean => {
  const type = (alert.type || '').toUpperCase()
  const code = (alert.code || '').toUpperCase()
  const severity = resolveAlertSeverity(alert.code, alert.details)
  return type.includes('ALARM') || type.includes('ALERT') || code.includes('ALARM') || severity === 'critical'
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

    if (sourceFilter.value) {
      const source = String(alert.source || '').toLowerCase()
      if (source !== sourceFilter.value) return false
    }

    if (severityFilter.value) {
      const severity = String(alert.severity || resolveAlertSeverity(alert.code, alert.details)).toLowerCase()
      if (severity !== severityFilter.value) return false
    }

    if (categoryFilter.value) {
      const category = String(alert.category || alert.details?.category || '').toLowerCase()
      if (category !== categoryFilter.value) return false
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
        getAlertMessage(alert),
        getAlertMeta(alert).title,
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
    if (!(err as any)?.response) {
      showToast(`Не удалось подтвердить алерт: ${extractHumanErrorMessage(err, 'Ошибка подтверждения')}`, 'error', TOAST_TIMEOUT.NORMAL)
    }
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
    if (!(err as any)?.response) {
      showToast(`Не удалось подтвердить выбранные алерты: ${extractHumanErrorMessage(err, 'Ошибка подтверждения')}`, 'error', TOAST_TIMEOUT.NORMAL)
    }
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

const selectedAlertMessage = computed(() => getAlertMessage(selectedAlert.value))

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

const severityToToastVariant = (severity: AlertSeverity): 'info' | 'warning' | 'error' => {
  if (severity === 'critical' || severity === 'error') return 'error'
  if (severity === 'warning') return 'warning'
  return 'info'
}

const getAlertToastKey = (alert: AlertRecord): string => {
  const dedupeFromBackend = String(alert.details?.dedupe_key || '').trim()
  if (dedupeFromBackend) return dedupeFromBackend
  return [
    String(alert.code || alert.type || 'unknown'),
    String(alert.zone_id || 'global'),
    String(alert.details?.node_uid || alert.details?.hardware_id || 'node'),
  ].join('|')
}

const shouldSuppressAlertToast = (alert: AlertRecord): boolean => {
  const windowMs = toastSuppressionMs.value
  if (windowMs <= 0) return false

  const now = Date.now()
  for (const [key, timestamp] of recentAlertToastAt.entries()) {
    if (now - timestamp > windowMs) {
      recentAlertToastAt.delete(key)
    }
  }

  const key = getAlertToastKey(alert)
  const prevTimestamp = recentAlertToastAt.get(key)
  if (prevTimestamp && now - prevTimestamp < windowMs) {
    return true
  }
  recentAlertToastAt.set(key, now)
  return false
}

const normalizeSuppressionSec = (value: unknown): number => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 30
  return Math.min(600, Math.max(0, Math.floor(parsed)))
}

const applyToastSuppressionFromStorage = (): boolean => {
  if (typeof window === 'undefined') return false
  const raw = window.localStorage.getItem(ALERT_TOAST_SUPPRESSION_KEY)
  if (!raw) return false
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return false
  isSyncingSuppressionPreference.value = true
  skipSuppressionPersistCount += 1
  toastSuppressionSec.value = normalizeSuppressionSec(parsed)
  isSyncingSuppressionPreference.value = false
  return true
}

const loadToastSuppressionPreference = async (): Promise<void> => {
  const hasLocalFallback = applyToastSuppressionFromStorage()
  try {
    const response = await api.get('/settings/preferences')
    const fromProfile = response?.data?.data?.alert_toast_suppression_sec
    isSyncingSuppressionPreference.value = true
    skipSuppressionPersistCount += 1
    toastSuppressionSec.value = normalizeSuppressionSec(fromProfile)
    isSyncingSuppressionPreference.value = false
  } catch (err) {
    logger.warn('[Alerts] Failed to load toast suppression preference from profile', err)
    if (!hasLocalFallback) {
      isSyncingSuppressionPreference.value = true
      skipSuppressionPersistCount += 1
      toastSuppressionSec.value = 30
      isSyncingSuppressionPreference.value = false
    }
  }
}

const persistToastSuppressionPreference = async (value: number): Promise<void> => {
  try {
    await api.patch('/settings/preferences', {
      alert_toast_suppression_sec: value,
    })
  } catch (err) {
    logger.warn('[Alerts] Failed to persist toast suppression preference', err)
  }
}

watch(toastSuppressionSec, (value) => {
  const normalized = normalizeSuppressionSec(value)
  if (normalized !== value) {
    toastSuppressionSec.value = normalized
    return
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(ALERT_TOAST_SUPPRESSION_KEY, String(normalized))
  }
  if (skipSuppressionPersistCount > 0) {
    skipSuppressionPersistCount -= 1
    return
  }
  if (isSyncingSuppressionPreference.value) return
  if (suppressionPersistTimer) {
    clearTimeout(suppressionPersistTimer)
  }
  suppressionPersistTimer = setTimeout(() => {
    persistToastSuppressionPreference(normalized)
  }, 350)
})

let unsubscribeAlerts: (() => void) | null = null

const loadAlertCatalog = async (): Promise<void> => {
  try {
    const response = await api.get('/api/alerts/catalog')
    const items = response?.data?.data?.items
    if (!Array.isArray(items)) return

    const map: Record<string, AlertCodeMeta> = {}
    items.forEach((item: AlertCatalogItem) => {
      const code = String(item?.code || '').trim().toLowerCase()
      if (!code) return
      map[code] = {
        title: item.title || 'Системное предупреждение',
        description: item.description || 'Сервис сообщил о состоянии, которое требует проверки.',
        recommendation: item.recommendation || 'Проверьте детали алерта и журналы сервиса.',
        severity: (item.severity || 'warning') as AlertSeverity,
      }
    })
    catalogMetaByCode.value = map
  } catch (err) {
    logger.warn('[Alerts] Failed to load alert catalog', err)
  }
}

onMounted(() => {
  loadToastSuppressionPreference()
  loadAlertCatalog()
  unsubscribeAlerts = subscribeAlerts((event) => {
    const payload = event as AlertRecord
    if (payload?.id) {
      alertsStore.upsert(payload as Alert)
      if (!isResolved(payload) && !shouldSuppressAlertToast(payload)) {
        const meta = getAlertMeta(payload)
        const severity = resolveAlertSeverity(payload.code, payload.details)
        showToast(
          getAlertMessage(payload),
          severityToToastVariant(severity),
          TOAST_TIMEOUT.NORMAL,
          {
            title: meta.title,
            allowDuplicates: true,
          }
        )
      }
    }
  })
})

onUnmounted(() => {
  if (suppressionPersistTimer) {
    clearTimeout(suppressionPersistTimer)
    suppressionPersistTimer = null
  }
  unsubscribeAlerts?.()
  unsubscribeAlerts = null
})
</script>
