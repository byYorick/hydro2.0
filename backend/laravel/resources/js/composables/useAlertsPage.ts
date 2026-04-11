import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import { logger } from '@/utils/logger'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useUrlState } from '@/composables/useUrlState'
import { useAlertsStore } from '@/stores/alerts'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { resolveAlertCodeMeta, resolveAlertSeverity, type AlertSeverity, type AlertCodeMeta } from '@/constants/alertErrorMap'
import { extractHumanErrorMessage } from '@/utils/errorMessage'
import { resolveHumanErrorMessage } from '@/utils/errorCatalog'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import type { WsEventPayload } from '@/ws/subscriptionTypes'
import type { Alert } from '@/types/Alert'

interface AlertZoneOption {
  id: number
  name: string
}

export interface AlertRecord extends Omit<Alert, 'zone'> {
  details?: Record<string, unknown> | null
  code?: string
  source?: string
  message?: string
  zone?: { id: number; name: string } | undefined
}

interface PageProps {
  alerts?: AlertRecord[]
  zones?: AlertZoneOption[]
  [key: string]: unknown
}

const ALERT_TOAST_SUPPRESSION_KEY = 'hydro.alerts.toastSuppressionSec'

export function useAlertsPage() {
  const page = usePage<PageProps>()
  const alertsStore = useAlertsStore()
  const { showToast } = useToast()

  // ── Toast suppression ────────────────────────────────────────────────────
  const toastSuppressionSec = ref(30)
  const isSyncingSuppressionPreference = ref(false)
  let skipSuppressionPersistCount = 0
  const recentAlertToastAt = new Map<string, number>()
  const toastSuppressionMs = computed(() => Math.max(0, Math.floor(Number(toastSuppressionSec.value) || 0) * 1000))
  let suppressionPersistTimer: ReturnType<typeof setTimeout> | null = null

  // ── URL filters ──────────────────────────────────────────────────────────
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

  // ── Store bootstrap ──────────────────────────────────────────────────────
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
  const accessibleZones = computed<AlertZoneOption[]>(() => {
    return Array.isArray(page.props.zones) ? page.props.zones : []
  })
  const accessibleZoneIds = computed<number[]>(() => {
    return accessibleZones.value
      .map((zone) => Number(zone?.id))
      .filter((zoneId) => Number.isInteger(zoneId) && zoneId > 0)
  })
  const catalogMetaByCode = ref<Record<string, AlertCodeMeta>>({})

  const isRefreshing = ref(false)
  const isInitialLoading = computed(() => isRefreshing.value && alerts.value.length === 0)

  // ── Data loading ─────────────────────────────────────────────────────────
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

      const list = await api.alerts.list(params)
      alertsStore.setAll(list)
    } catch (err) {
      logger.error('[Alerts] Failed to load alerts', err)
      if (!(err as { response?: unknown })?.response) {
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

  // ── Zone options for filter ──────────────────────────────────────────────
  const zoneOptions = computed(() => {
    const map = new Map<number, string>()
    accessibleZones.value.forEach((zone) => {
      if (zone?.id) {
        map.set(zone.id, zone.name || `Zone #${zone.id}`)
      }
    })
    alerts.value.forEach((alert) => {
      const zone = alert.zone
      if (zone?.id) {
        map.set(zone.id, zone.name || `Zone #${zone.id}`)
      }
    })
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }))
  })

  const searchNeedle = computed(() => searchQuery.value.trim().toLowerCase())

  // ── Alert metadata helpers ───────────────────────────────────────────────
  const getAlertMeta = (alert?: AlertRecord | null): AlertCodeMeta => {
    if (alert?.title || alert?.description || alert?.recommendation) {
      return {
        title: String(alert.title || 'Системное предупреждение'),
        description: String(alert.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
        recommendation: String(alert.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
        severity: resolveAlertSeverity(alert.code, alert.details),
      }
    }

    const details = alert?.details as Record<string, unknown> | null | undefined
    if (details?.title || details?.description || details?.recommendation) {
      return {
        title: String(details.title || 'Системное предупреждение'),
        description: String(details.description || 'Сервис сообщил о состоянии, которое требует проверки.'),
        recommendation: String(details.recommendation || 'Проверьте детали алерта и журналы сервиса.'),
        severity: resolveAlertSeverity(alert?.code, alert?.details),
      }
    }

    const code = String(alert?.code || '').trim().toLowerCase()
    if (code && catalogMetaByCode.value[code]) {
      return catalogMetaByCode.value[code]
    }
    return resolveAlertCodeMeta(alert?.code)
  }

  const getAlertMessage = (alert?: AlertRecord | null): string => {
    if (!alert) return ''
    const details = alert.details as Record<string, unknown> | null | undefined
    const messageFromPayload = String(
      alert.message
      || details?.message
      || details?.reason
      || details?.error_message
      || ''
    ).trim()
    const localized = resolveHumanErrorMessage({
      code: String(details?.error_code || alert.code || '').trim() || null,
      message: messageFromPayload || null,
    })
    if (localized) return localized
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

  // ── Filtering ────────────────────────────────────────────────────────────
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
        const category = String(alert.category || (alert.details as Record<string, unknown>)?.category || '').toLowerCase()
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

  // ── Selection ────────────────────────────────────────────────────────────
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

  // ── Resolve (acknowledge) ────────────────────────────────────────────────
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
      const updated = await api.alerts.acknowledge(confirm.value.alertId) as AlertRecord
      applyResolved(confirm.value.alertId, updated)
    } catch (err) {
      logger.error('[Alerts] Failed to resolve alert', err)
      if (!(err as { response?: unknown })?.response) {
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
        const updated = await api.alerts.acknowledge(id) as AlertRecord
        applyResolved(id, updated)
      }))
    } catch (err) {
      logger.error('[Alerts] Failed to resolve alerts', err)
      if (!(err as { response?: unknown })?.response) {
        showToast(`Не удалось подтвердить выбранные алерты: ${extractHumanErrorMessage(err, 'Ошибка подтверждения')}`, 'error', TOAST_TIMEOUT.NORMAL)
      }
    } finally {
      bulkConfirm.value = { open: false, loading: false }
      selectedIds.value = new Set()
    }
  }

  // ── Details side panel ───────────────────────────────────────────────────
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

  // ── Utility functions ────────────────────────────────────────────────────
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
    const dedupeFromBackend = String((alert.details as Record<string, unknown>)?.dedupe_key || '').trim()
    if (dedupeFromBackend) return dedupeFromBackend
    return [
      String(alert.code || alert.type || 'unknown'),
      String(alert.zone_id || 'global'),
      String((alert.details as Record<string, unknown>)?.node_uid || (alert.details as Record<string, unknown>)?.hardware_id || 'node'),
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

  // ── Toast suppression persistence ────────────────────────────────────────
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
      const prefs = await api.settings.getPreferences()
      const fromProfile = prefs?.alert_toast_suppression_sec
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
      await api.settings.updatePreferences({
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

  // ── Alert catalog ────────────────────────────────────────────────────────
  const loadAlertCatalog = async (): Promise<void> => {
    try {
      const response = await api.alerts.catalog()
      const items = response?.items
      if (!Array.isArray(items)) return

      const map: Record<string, AlertCodeMeta> = {}
      items.forEach((item) => {
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

  // ── WebSocket subscription ────────────────────────────────────────────────
  const ALERT_EVENT_NAMES = ['.AlertCreated', '.App\\Events\\AlertCreated', '.AlertUpdated', '.App\\Events\\AlertUpdated'] as const
  const realtimeUnsubscribers: Array<() => void> = []

  const handleRealtimeAlert = (event: AlertRecord): void => {
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
  }

  const handleRealtimeAlertPayload = (payload: WsEventPayload): void => {
    handleRealtimeAlert(payload as unknown as AlertRecord)
  }

  onMounted(() => {
    loadToastSuppressionPreference()
    loadAlertCatalog()
    const alertEventHandlers = Object.fromEntries(
      ALERT_EVENT_NAMES.map((eventName) => [eventName, handleRealtimeAlertPayload])
    )

    realtimeUnsubscribers.push(
      subscribeManagedChannelEvents({
        channelName: 'hydro.alerts',
        eventHandlers: alertEventHandlers,
        componentTag: 'useAlertsPage:global-alerts',
      })
    )

    accessibleZoneIds.value.forEach((zoneId) => {
      realtimeUnsubscribers.push(
        subscribeManagedChannelEvents({
          channelName: `hydro.zones.${zoneId}`,
          eventHandlers: alertEventHandlers,
          componentTag: `useAlertsPage:zone-${zoneId}`,
        })
      )
    })
  })

  onUnmounted(() => {
    if (suppressionPersistTimer) {
      clearTimeout(suppressionPersistTimer)
      suppressionPersistTimer = null
    }
    while (realtimeUnsubscribers.length > 0) {
      const unsubscribe = realtimeUnsubscribers.pop()
      unsubscribe?.()
    }
  })

  return {
    // filters
    statusFilter,
    zoneIdFilter,
    sourceFilter,
    severityFilter,
    categoryFilter,
    searchQuery,
    recentOnly,
    alarmsOnly,
    // data
    alerts,
    filteredAlerts,
    zoneOptions,
    selectableAlerts,
    isRefreshing,
    isInitialLoading,
    catalogMetaByCode,
    // selection
    selectedIds,
    selectedCount,
    allVisibleSelected,
    toggleSelection,
    toggleSelectAll,
    // resolve
    confirm,
    bulkConfirm,
    openResolve,
    closeConfirm,
    doResolve,
    resolveSelected,
    // side panel
    selectedAlertId,
    selectedAlert,
    selectedAlertMessage,
    detailsJson,
    openDetails,
    closeDetails,
    // toast suppression
    toastSuppressionSec,
    toastSuppressionMs,
    isSyncingSuppressionPreference,
    // utility functions
    isResolved,
    isAlarm,
    formatDate,
    getAlertMeta,
    getAlertMessage,
    shouldSuppressAlertToast,
    normalizeSuppressionSec,
    // data actions
    loadAlerts,
  }
}
