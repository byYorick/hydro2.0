<template>
  <div class="space-y-2">

    <!-- Компактная шапка -->
    <div class="flex flex-wrap items-center gap-1.5 px-1">
      <span class="font-headline text-sm font-bold text-[color:var(--text-primary)]">Алерты</span>
      <Badge variant="danger" size="sm">{{ filteredAlerts.length }}</Badge>
      <div class="mx-1 h-3.5 w-px bg-[color:var(--border-muted)]"></div>
      <button
        v-for="status in statusOptions"
        :key="status.value"
        type="button"
        class="h-5 px-2 rounded text-[10px] font-semibold uppercase tracking-wide border transition-colors"
        :class="selectedStatus === status.value
          ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
          : 'border-transparent text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-muted)]'"
        @click="selectedStatus = status.value"
      >
        {{ status.label }}
      </button>
      <div class="ml-auto flex items-center">
        <input
          :value="query"
          class="input-field h-6 w-32 text-xs px-2"
          placeholder="Поиск..."
          @input="query = ($event.target as HTMLInputElement).value"
        />
      </div>
    </div>

    <!-- Список алертов -->
    <section class="surface-card border border-[color:var(--border-muted)] rounded-xl p-2">
      <div
        v-if="filteredAlerts.length === 0"
        class="py-6 text-center text-[11px] text-[color:var(--text-dim)]"
      >
        Алерты по текущим фильтрам не найдены
      </div>

      <div v-else-if="useVirtual" class="h-[calc(100vh-260px)]">
        <VirtualList
          :items="filteredAlerts"
          :item-size="96"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <button
              type="button"
              class="w-full text-left rounded-xl px-3 py-2 border border-transparent hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-muted)]/30 transition-colors"
              :data-testid="`zone-alert-row-${item.id}`"
              @click="openDetails(item)"
            >
              <AlertRow :item="item" />
            </button>
          </template>
        </VirtualList>
      </div>

      <div v-else class="max-h-[calc(100vh-260px)] space-y-0.5 overflow-y-auto pr-0.5">
        <button
          v-for="item in filteredAlerts"
          :key="item.id"
          type="button"
          class="w-full text-left rounded-xl px-3 py-2 border border-transparent hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-muted)]/30 transition-colors"
          :data-testid="`zone-alert-row-${item.id}`"
          @click="openDetails(item)"
        >
          <AlertRow :item="item" />
        </button>
      </div>
    </section>

    <AlertDetailModal
      :open="Boolean(selectedAlert)"
      :alert="selectedAlert"
      :resolve-loading="resolveLoading"
      @close="closeDetails"
      @resolve="resolveSelectedAlert"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import VirtualList from '@/Components/VirtualList.vue'
import AlertRow from '@/Components/Alerts/AlertRow.vue'
import AlertDetailModal from '@/Components/Alerts/AlertDetailModal.vue'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import { logger } from '@/utils/logger'
import type { Alert } from '@/types/Alert'
import {
  detailsToString,
  getAlertDescription,
  getAlertMessage,
  getAlertTitle,
  normalizeAlertStatus,
} from '@/utils/alertMeta'

interface Props {
  alerts: Alert[]
  zoneId: number | null
}

const props = defineProps<Props>()

const { showToast } = useToast()

const statusOptions: Array<{ value: 'ALL' | 'ACTIVE' | 'RESOLVED'; label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ACTIVE', label: 'Активные' },
  { value: 'RESOLVED', label: 'Решённые' },
]

const selectedStatus = ref<'ALL' | 'ACTIVE' | 'RESOLVED'>('ALL')
const query = ref('')
const localAlerts = ref<Alert[]>(Array.isArray(props.alerts) ? [...props.alerts] : [])
const selectedAlertId = ref<number | null>(null)
const resolveLoading = ref(false)

watch(
  () => props.alerts,
  (nextAlerts) => {
    localAlerts.value = Array.isArray(nextAlerts) ? [...nextAlerts] : []
    if (selectedAlertId.value && !localAlerts.value.some((alert) => alert.id === selectedAlertId.value)) {
      selectedAlertId.value = null
    }
  },
  { deep: true },
)

const queryLower = computed(() => query.value.toLowerCase())

const filteredAlerts = computed(() => {
  return localAlerts.value.filter((alert) => {
    const normalizedStatus = normalizeAlertStatus(alert.status)
    const matchesStatus = selectedStatus.value === 'ALL' ? true : normalizedStatus === selectedStatus.value
    const searchSource = [
      alert.type || '',
      alert.code || '',
      getAlertTitle(alert),
      getAlertMessage(alert),
      getAlertDescription(alert),
      detailsToString(alert.details),
    ].join(' ').toLowerCase()
    const matchesQuery = queryLower.value ? searchSource.includes(queryLower.value) : true
    return matchesStatus && matchesQuery
  })
})

const useVirtual = computed(() => filteredAlerts.value.length > 200)

const selectedAlert = computed<Alert | null>(() => {
  if (!selectedAlertId.value) return null
  return localAlerts.value.find((alert) => alert.id === selectedAlertId.value) ?? null
})

const openDetails = (alert: Alert): void => {
  selectedAlertId.value = alert.id
}

const closeDetails = (): void => {
  if (resolveLoading.value) return
  selectedAlertId.value = null
}

const applyResolved = (id: number, updated?: Alert): void => {
  localAlerts.value = localAlerts.value.map((alert) => {
    if (alert.id !== id) return alert
    if (updated) return { ...alert, ...updated }
    return {
      ...alert,
      status: 'resolved',
      resolved_at: new Date().toISOString(),
    }
  })
}

const resolveSelectedAlert = async (): Promise<void> => {
  if (!selectedAlert.value || normalizeAlertStatus(selectedAlert.value.status) === 'RESOLVED' || resolveLoading.value) return
  resolveLoading.value = true

  try {
    const updated = await api.alerts.acknowledge(selectedAlert.value.id)
    applyResolved(selectedAlert.value.id, updated)
    showToast('Алерт помечен как решённый', 'success', TOAST_TIMEOUT.NORMAL)
    selectedAlertId.value = null
  } catch (error) {
    logger.error('[ZoneAlertsTab] Failed to resolve alert', error)
    showToast(`Не удалось закрыть алерт: ${extractHumanErrorMessage(error, 'Ошибка подтверждения')}`, 'error', TOAST_TIMEOUT.LONG)
  } finally {
    resolveLoading.value = false
  }
}
</script>
