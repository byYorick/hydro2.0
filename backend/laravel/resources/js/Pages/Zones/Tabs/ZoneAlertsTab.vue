<template>
  <div class="space-y-2">
    <!-- Компактная шапка -->
    <div class="flex flex-wrap items-center gap-1.5 px-1">
      <span class="font-headline text-sm font-bold text-[color:var(--text-primary)]">Алерты</span>
      <Badge
        variant="danger"
        size="sm"
      >
        {{ filteredAlerts.length }}
      </Badge>
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

      <div
        v-else
        class="max-h-[calc(100vh-260px)] space-y-3 overflow-y-auto pr-0.5"
      >
        <section
          v-for="section in alertSections"
          :key="section.id"
          class="space-y-0.5"
          :data-testid="section.testId"
        >
          <div class="flex flex-wrap items-center gap-1.5 px-1 py-1">
            <span class="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
              {{ section.title }}
            </span>
            <Badge
              :variant="section.badgeVariant"
              size="xs"
            >
              {{ section.items.length }}
            </Badge>
            <span class="text-[11px] text-[color:var(--text-dim)]">
              {{ section.description }}
            </span>
          </div>
          <div class="space-y-0.5">
            <button
              v-for="item in section.items"
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
  sortAlertsBySeverityAndCreatedAt,
} from '@/utils/alertMeta'
import {
  isAutomationBlockingCode,
  isSafetyCriticalCode,
  PROCESS_STOPPING_SECTION_TITLE,
} from '@/utils/automationBlock'

interface Props {
  alerts: Alert[]
  zoneId: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'policy-alert-resolved'): void
}>()

const { showToast } = useToast()

const statusOptions: Array<{ value: 'ALL' | 'ACTIVE' | 'RESOLVED'; label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ACTIVE', label: 'Активные' },
  { value: 'RESOLVED', label: 'Решённые' },
]

const selectedStatus = ref<'ALL' | 'ACTIVE' | 'RESOLVED'>('ACTIVE')
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

interface AlertSection {
  id: 'automation_block' | 'safety' | 'other' | 'resolved'
  title: string
  description: string
  badgeVariant: 'danger' | 'warning' | 'neutral' | 'success'
  testId: string
  items: Alert[]
}

const alertSections = computed<AlertSection[]>(() => {
  const automationBlock: Alert[] = []
  const safety: Alert[] = []
  const other: Alert[] = []
  const resolved: Alert[] = []

  for (const alert of filteredAlerts.value) {
    if (normalizeAlertStatus(alert.status) === 'RESOLVED') {
      resolved.push(alert)
      continue
    }

    if (isAutomationBlockingCode(alert.code)) {
      automationBlock.push(alert)
      continue
    }

    if (isSafetyCriticalCode(alert.code)) {
      safety.push(alert)
      continue
    }

    other.push(alert)
  }

  const sections: AlertSection[] = []
  if (automationBlock.length) {
    sections.push({
      id: 'automation_block',
      title: PROCESS_STOPPING_SECTION_TITLE.automation_block,
      description: 'Policy-managed алерты, которые останавливают AE3 до ручного решения.',
      badgeVariant: 'danger',
      testId: 'zone-alert-section-automation-block',
      items: sortAlertsBySeverityAndCreatedAt(automationBlock),
    })
  }
  if (safety.length) {
    sections.push({
      id: 'safety',
      title: PROCESS_STOPPING_SECTION_TITLE.safety,
      description: 'Алерты железа и исполнительных каналов с safety-риском.',
      badgeVariant: 'danger',
      testId: 'zone-alert-section-safety',
      items: sortAlertsBySeverityAndCreatedAt(safety),
    })
  }
  if (other.length) {
    sections.push({
      id: 'other',
      title: PROCESS_STOPPING_SECTION_TITLE.other,
      description: 'Активные алерты без process-stopping признака.',
      badgeVariant: 'neutral',
      testId: 'zone-alert-section-other',
      items: sortAlertsBySeverityAndCreatedAt(other),
    })
  }
  if (resolved.length) {
    sections.push({
      id: 'resolved',
      title: PROCESS_STOPPING_SECTION_TITLE.resolved,
      description: 'Закрытые алерты по текущему фильтру.',
      badgeVariant: 'success',
      testId: 'zone-alert-section-resolved',
      items: sortAlertsBySeverityAndCreatedAt(resolved),
    })
  }

  return sections
})

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
    const resolvedAlert = selectedAlert.value
    const updated = await api.alerts.acknowledge(resolvedAlert.id)
    applyResolved(resolvedAlert.id, updated)
    if (isAutomationBlockingCode(resolvedAlert.code)) {
      emit('policy-alert-resolved')
    }
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
