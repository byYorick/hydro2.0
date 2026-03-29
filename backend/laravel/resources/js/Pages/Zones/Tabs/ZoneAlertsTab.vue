<template>
  <div class="space-y-4">
    <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
          <button
            v-for="status in statusOptions"
            :key="status.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="selectedStatus === status.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="selectedStatus = status.value"
          >
            {{ status.label }}
          </button>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="query"
            class="input-field h-9 w-full sm:w-72"
            placeholder="Поиск по коду, сообщению, details..."
          />
        </div>
      </div>
    </section>

    <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
      <div
        v-if="filteredAlerts.length === 0"
        class="text-sm text-[color:var(--text-dim)] text-center py-6"
      >
        Алерты по текущим фильтрам не найдены
      </div>

      <div
        v-else
        class="h-[520px]"
      >
        <VirtualList
          v-if="useVirtual"
          :items="filteredAlerts"
          :item-size="96"
          class="h-full"
          key-field="id"
        >
          <template #default="{ item }">
            <button
              type="button"
              class="w-full text-left rounded-xl px-3 py-3 border border-transparent hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-muted)]/30 transition-colors"
              :data-testid="`zone-alert-row-${item.id}`"
              @click="openDetails(item)"
            >
              <AlertRowContent :item="item" />
            </button>
          </template>
        </VirtualList>

        <div
          v-else
          class="space-y-1 max-h-[520px] overflow-y-auto"
        >
          <button
            v-for="item in filteredAlerts"
            :key="item.id"
            type="button"
            class="w-full text-left rounded-xl px-3 py-3 border border-transparent hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-muted)]/30 transition-colors"
            :data-testid="`zone-alert-row-${item.id}`"
            @click="openDetails(item)"
          >
            <AlertRowContent :item="item" />
          </button>
        </div>
      </div>
    </section>

    <Modal
      :open="Boolean(selectedAlert)"
      title="Детали алерта"
      size="large"
      data-testid="zone-alert-details-modal"
      @close="closeDetails"
    >
      <div
        v-if="selectedAlert"
        class="space-y-4 text-sm"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Тип</div>
            <div class="font-semibold text-[color:var(--text-primary)]">{{ getAlertTitle(selectedAlert) }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Статус</div>
            <div class="font-semibold text-[color:var(--text-primary)]">{{ translateStatus(selectedAlert.status) }}</div>
          </div>
          <div
            v-if="selectedAlert.code"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Код</div>
            <div class="font-mono text-[color:var(--text-primary)]">{{ selectedAlert.code }}</div>
          </div>
          <div
            v-if="selectedAlert.source"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Источник</div>
            <div class="text-[color:var(--text-primary)]">{{ selectedAlert.source }}</div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Создан</div>
            <div class="text-[color:var(--text-primary)]">{{ formatDate(selectedAlert.created_at) }}</div>
          </div>
          <div
            v-if="selectedAlert.resolved_at"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Решён</div>
            <div class="text-[color:var(--text-primary)]">{{ formatDate(selectedAlert.resolved_at) }}</div>
          </div>
        </div>

        <div
          v-if="selectedAlertMessage"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Сообщение</div>
          <div class="text-[color:var(--text-primary)]">{{ selectedAlertMessage }}</div>
        </div>

        <div
          v-if="selectedAlertDescription"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Описание</div>
          <div class="text-[color:var(--text-primary)]">{{ selectedAlertDescription }}</div>
        </div>

        <div
          v-if="selectedAlertRecommendation"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Что делать</div>
          <div class="text-[color:var(--text-primary)]">{{ selectedAlertRecommendation }}</div>
        </div>

        <div
          v-if="detailsJson"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Payload details</div>
          <pre class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs overflow-x-auto text-[color:var(--text-primary)]">{{ detailsJson }}</pre>
        </div>
      </div>

      <template #footer>
        <Button
          v-if="selectedAlert && !isResolved(selectedAlert)"
          variant="success"
          :disabled="resolveLoading"
          data-testid="zone-alert-resolve-button"
          @click="resolveSelectedAlert"
        >
          {{ resolveLoading ? 'Решаю...' : 'Решить' }}
        </Button>
      </template>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import VirtualList from '@/Components/VirtualList.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { resolveAlertCodeMeta } from '@/constants/alertErrorMap'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import { translateStatus } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import type { Alert } from '@/types/Alert'

interface Props {
  alerts: Alert[]
  zoneId: number | null
}

const props = defineProps<Props>()

const { patch } = useApi()
const { showToast } = useToast()

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

const statusOptions: Array<{ value: 'ALL' | 'ACTIVE' | 'RESOLVED', label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ACTIVE', label: 'Активные' },
  { value: 'RESOLVED', label: 'Решённые' },
]

const queryLower = computed(() => query.value.toLowerCase())

const statusNormalized = (status: string | undefined): 'ACTIVE' | 'RESOLVED' | 'OTHER' => {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'ACTIVE') return 'ACTIVE'
  if (normalized === 'RESOLVED') return 'RESOLVED'
  return 'OTHER'
}

const detailsToString = (details: Alert['details']): string => {
  if (!details || typeof details !== 'object') return ''
  try {
    return JSON.stringify(details)
  } catch {
    return ''
  }
}

const getAlertMeta = (alert?: Alert | null) => {
  const details = alert?.details as Record<string, unknown> | null | undefined
  if (alert?.title || alert?.description || alert?.recommendation) {
    return {
      title: String(alert.title || 'Системное предупреждение'),
      description: String(alert.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
      recommendation: String(alert.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
    }
  }
  if (details?.title || details?.description || details?.recommendation) {
    return {
      title: String(details.title || 'Системное предупреждение'),
      description: String(details.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
      recommendation: String(details.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
    }
  }
  return resolveAlertCodeMeta(alert?.code)
}

const getAlertMessage = (alert: Alert): string => {
  const details = alert.details as Record<string, unknown> | null | undefined
  const rawMessage = String(
    alert.message
    || details?.message
    || details?.reason
    || details?.error
    || details?.error_message
    || ''
  ).trim()
  const localized = resolveHumanErrorMessage({
    code: String(details?.error_code || alert.code || '').trim() || null,
    message: rawMessage || null,
  })
  if (localized) return localized
  return rawMessage
}

const getAlertTitle = (alert: Alert): string => {
  return getAlertMeta(alert).title || alert.type || 'Системное предупреждение'
}

const getAlertDescription = (alert: Alert): string => {
  return getAlertMeta(alert).description || ''
}

const getAlertRecommendation = (alert: Alert): string => {
  return getAlertMeta(alert).recommendation || ''
}

const filteredAlerts = computed(() => {
  return localAlerts.value.filter((alert) => {
    const normalizedStatus = statusNormalized(alert.status)
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

const selectedAlertMessage = computed(() => (
  selectedAlert.value ? getAlertMessage(selectedAlert.value) : ''
))
const selectedAlertDescription = computed(() => (
  selectedAlert.value ? getAlertDescription(selectedAlert.value) : ''
))
const selectedAlertRecommendation = computed(() => (
  selectedAlert.value ? getAlertRecommendation(selectedAlert.value) : ''
))

const detailsJson = computed(() => {
  if (!selectedAlert.value?.details) return ''
  try {
    return JSON.stringify(selectedAlert.value.details, null, 2)
  } catch {
    return String(selectedAlert.value.details)
  }
})

const alertStatusVariant = (status: Alert['status']): 'danger' | 'success' | 'warning' => {
  const normalized = statusNormalized(status)
  if (normalized === 'ACTIVE') return 'danger'
  if (normalized === 'RESOLVED') return 'success'
  return 'warning'
}

const formatDate = (value?: string): string => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

const isResolved = (alert: Alert): boolean => statusNormalized(alert.status) === 'RESOLVED'

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
  if (!selectedAlert.value || isResolved(selectedAlert.value) || resolveLoading.value) return
  resolveLoading.value = true

  try {
    const response = await patch<{ data?: Alert }>(`/api/alerts/${selectedAlert.value.id}/ack`, {})
    const updated = response?.data?.data
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

const AlertRowContent = defineComponent({
  name: 'AlertRowContent',
  props: {
    item: {
      type: Object as () => Alert,
      required: true,
    },
  },
  setup(rowProps) {
    return () => h('div', {
      class: 'text-sm text-[color:var(--text-muted)] flex items-start gap-3 border-b border-[color:var(--border-muted)] pb-2',
    }, [
      h(Badge, { variant: alertStatusVariant(rowProps.item.status), class: 'text-xs shrink-0 mt-0.5' }, () => translateStatus(rowProps.item.status)),
      h('div', { class: 'flex-1 min-w-0 space-y-1' }, [
        h('div', { class: 'flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]' }, [
          h('span', {}, formatDate(rowProps.item.created_at)),
          h('span', { class: 'font-semibold text-[color:var(--text-primary)]' }, getAlertTitle(rowProps.item)),
          rowProps.item.code ? h('span', { class: 'font-mono text-[color:var(--text-dim)]' }, rowProps.item.code) : null,
        ]),
        h('div', { class: 'text-sm text-[color:var(--text-primary)] break-words' }, getAlertMessage(rowProps.item) || 'Без сообщения'),
        h('div', { class: 'text-xs text-[color:var(--text-dim)]' }, isResolved(rowProps.item)
          ? `Решён: ${formatDate(rowProps.item.resolved_at || rowProps.item.updated_at)}`
          : 'Нажмите, чтобы открыть детали и закрыть алерт'),
      ]),
    ])
  },
})
</script>
