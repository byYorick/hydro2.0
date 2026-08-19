import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import { useCommands } from '@/composables/useCommands'
import { useTelemetry } from '@/composables/useTelemetry'
import { useZones } from '@/composables/useZones'
import { api } from '@/services/api'
import { useWebSocket } from '@/composables/useWebSocket'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useModal } from '@/composables/useModal'
import { useLoading } from '@/composables/useLoading'
import { useUrlState } from '@/composables/useUrlState'
import { useToast } from '@/composables/useToast'
import { useZoneCycleActions } from '@/composables/useZoneCycleActions'
import { useZonePageState } from '@/composables/useZonePageState'
import { useZoneTelemetryChart } from '@/composables/useZoneTelemetryChart'
import { usePumpCalibrationActions } from '@/composables/usePumpCalibrationActions'
import { useRole } from '@/composables/useRole'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { ERROR_MESSAGES } from '@/constants/messages'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import { parseNodeTelemetryBatch } from '@/ws/nodeTelemetryPayload'
import type { CommandType } from '@/types'
import type { UserRole } from '@/types/User'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'

// ─── Local types ──────────────────────────────────────────────────────────────

interface LoadingState extends Record<string, boolean> {
  actionSubmit: boolean
  nextPhase: boolean
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  cycleChangeRecipe: boolean
  pumpCalibrationRun: boolean
  pumpCalibrationSave: boolean
}

// ─── Zone tabs (role layout) ──────────────────────────────────────────────────

export type ZoneTabId =
  | 'cycle'
  | 'telemetry'
  | 'automation'
  | 'scheduler'
  | 'events'
  | 'alerts'
  | 'devices'

export interface ZoneTabItem {
  id: ZoneTabId
  label: string
}

interface ZoneTabLayout {
  defaultTab: ZoneTabId
  primary: ZoneTabItem[]
  more: ZoneTabItem[]
}

const ALL_ZONE_TAB_IDS: ZoneTabId[] = [
  'cycle',
  'telemetry',
  'automation',
  'scheduler',
  'events',
  'alerts',
  'devices',
]

const ZONE_TAB_LABELS: Record<ZoneTabId, string> = {
  cycle: 'Цикл',
  telemetry: 'Телеметрия',
  automation: 'Автоматизация',
  scheduler: 'Планировщик',
  events: 'События',
  alerts: 'Тревоги',
  devices: 'Узлы',
}

function tab(id: ZoneTabId, label?: string): ZoneTabItem {
  return { id, label: label ?? ZONE_TAB_LABELS[id] }
}

const OPERATOR_ZONE_TAB_LAYOUT: ZoneTabLayout = {
  defaultTab: 'cycle',
  primary: [
    tab('cycle', 'Состояние'),
    tab('automation', 'Действия'),
    tab('alerts', 'Тревоги'),
    tab('events', 'История работ'),
  ],
  more: [
    tab('telemetry'),
    tab('scheduler'),
    tab('devices'),
  ],
}

const ZONE_TAB_LAYOUT_BY_ROLE: Record<UserRole, ZoneTabLayout> = {
  operator: OPERATOR_ZONE_TAB_LAYOUT,
  viewer: OPERATOR_ZONE_TAB_LAYOUT,
  agronomist: {
    defaultTab: 'cycle',
    primary: [
      tab('cycle', 'Цикл'),
      tab('automation', 'Раствор'),
      tab('telemetry', 'Телеметрия'),
      tab('alerts', 'Отклонения'),
    ],
    more: [
      tab('scheduler'),
      tab('devices'),
      tab('events'),
    ],
  },
  engineer: {
    defaultTab: 'devices',
    primary: [
      tab('devices'),
      tab('automation', 'Процесс'),
      tab('scheduler'),
      tab('events'),
      tab('telemetry'),
    ],
    more: [
      tab('cycle'),
    ],
  },
  admin: {
    defaultTab: 'alerts',
    primary: [
      tab('alerts', 'Тревоги'),
      tab('devices'),
      tab('events', 'Журнал'),
    ],
    more: [
      tab('cycle'),
      tab('automation', 'Раствор'),
      tab('scheduler'),
      tab('telemetry'),
    ],
  },
}

function isZoneTabId(value: string): value is ZoneTabId {
  return ALL_ZONE_TAB_IDS.includes(value as ZoneTabId)
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useZoneShowPage() {
  const { role } = useRole()

  const zoneTabLayout = computed<ZoneTabLayout>(() => {
    const currentRole = role.value
    if (currentRole && currentRole in ZONE_TAB_LAYOUT_BY_ROLE) {
      return ZONE_TAB_LAYOUT_BY_ROLE[currentRole]
    }
    return OPERATOR_ZONE_TAB_LAYOUT
  })

  const defaultTabId = computed<ZoneTabId>(() => zoneTabLayout.value.defaultTab)

  const activeTab = useUrlState<string>({
    key: 'tab',
    defaultValue: defaultTabId.value,
    parse: (value) => {
      const fallback = defaultTabId.value
      if (!value) return fallback
      return isZoneTabId(value) ? value : fallback
    },
    serialize: (value) => value,
  })

  const moreZoneTabs = computed<ZoneTabItem[]>(() => zoneTabLayout.value.more)

  const zoneTabs = computed<ZoneTabItem[]>(() => {
    const primary = zoneTabLayout.value.primary
    const activeId = activeTab.value
    if (primary.some((item) => item.id === activeId)) {
      return primary
    }
    const extra = moreZoneTabs.value.find((item) => item.id === activeId)
    if (extra) {
      return [...primary, extra]
    }
    return primary
  })

  const modals = useModal<{
    action: boolean
    growthCycle: boolean
    pumpCalibration: boolean
    attachNodes: boolean
    nodeConfig: boolean
  }>({
    action: false,
    growthCycle: false,
    pumpCalibration: false,
    attachNodes: false,
    nodeConfig: false,
  })

  const showActionModal = computed(() => modals.isModalOpen('action'))
  const showPumpCalibrationModal = computed(() => modals.isModalOpen('pumpCalibration'))
  const showAttachNodesModal = computed(() => modals.isModalOpen('attachNodes'))
  const showNodeConfigModal = computed(() => modals.isModalOpen('nodeConfig'))

  const currentActionType = ref<CommandType>('START_IRRIGATION')
  const selectedNodeId = ref<number | null>(null)
  const selectedNode = ref<any>(null)

  const { loading, setLoading } = useLoading<LoadingState>({
    actionSubmit: false,
    nextPhase: false,
    cyclePause: false,
    cycleResume: false,
    cycleHarvest: false,
    cycleAbort: false,
    cycleChangeRecipe: false,
    pumpCalibrationRun: false,
    pumpCalibrationSave: false,
  })

  // ─── Service dependencies ─────────────────────────────────────────────────

  const { showToast } = useToast()
  const { sendZoneCommand, reloadZoneAfterCommand, updateCommandStatus } = useCommands(showToast)
  const { fetchHistory, fetchHistoryWithNodes } = useTelemetry(showToast)
  const { reloadZone } = useZones(showToast)
  const { subscribeToZoneCommands } = useWebSocket(showToast)
  const { handleError } = useErrorHandler(showToast)
  const pumpCalibrationActions = usePumpCalibrationActions({
    getZoneId: () => zoneId.value,
    showToast,
    successTimeout: TOAST_TIMEOUT.NORMAL,
    runSuccessMessage: 'Запуск калибровки отправлен. После завершения введите фактический объём и сохраните.',
    saveSuccessMessage: 'Калибровка сохранена в конфигурации канала.',
    onRunSuccess: () => {
      setLoading('pumpCalibrationRun', false)
    },
    onSaveSuccess: async () => {
      reloadZone(zoneId.value as number, ['zone', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
    },
    onRunError: (error) => {
      handleError(error, { component: 'useZoneShowPage', action: 'pumpCalibrationRun', zoneId: zoneId.value })
    },
    onSaveError: (error) => {
      handleError(error, { component: 'useZoneShowPage', action: 'pumpCalibrationSave', zoneId: zoneId.value })
    },
  })
  const pumpCalibrationSaveSeq = pumpCalibrationActions.saveSeq
  const pumpCalibrationRunSeq = pumpCalibrationActions.runSeq
  const pumpCalibrationLastRunToken = pumpCalibrationActions.lastRunToken

  // ─── Sub-composables ──────────────────────────────────────────────────────

  const pageState = useZonePageState({
    reloadZoneAfterCommand,
    updateCommandStatus,
    reloadZone,
    subscribeToZoneCommands,
  })

  const hasSoilMoisture = computed(() => {
    return pageState.devices.value.some((d) =>
      (d.channels ?? []).some(
        (c) =>
          c.binding_role === 'soil_moisture_sensor' ||
          String(c.metric ?? '').toUpperCase() === 'SOIL_MOISTURE'
      )
    )
  })

  const chart = useZoneTelemetryChart(pageState.zoneId, {
    fetchHistory,
    fetchHistoryWithNodes: fetchHistoryWithNodes as (
      zoneId: number,
      metric: 'SOIL_MOISTURE',
      params: { from?: string; to: string },
      forceRefresh?: boolean,
    ) => Promise<Record<number, Array<{ ts: number; value: number }>>>,
    hasSoilMoisture,
  })

  const { zoneId, zone, activeGrowCycle, reloadZonePageProps } = pageState
  let stopTelemetryRealtimeSubscription: (() => void) | null = null

  const handleRealtimeTelemetryBatch = (payload: unknown): void => {
    const updates = parseNodeTelemetryBatch(payload)
    updates.forEach((update) => {
      pageState.applyRealtimeTelemetryPoint(update.metric_type, update.value, update.ts)
      chart.appendRealtimePoint(
        update.metric_type,
        {
          ts: update.ts,
          value: update.value,
        },
        update.node_id,
      )
    })
  }

  const subscribeTelemetryRealtime = (targetZoneId: number): void => {
    if (stopTelemetryRealtimeSubscription) {
      stopTelemetryRealtimeSubscription()
      stopTelemetryRealtimeSubscription = null
    }

    stopTelemetryRealtimeSubscription = subscribeManagedChannelEvents({
      channelName: `hydro.zones.${targetZoneId}`,
      componentTag: 'Zones/Show.telemetry',
      eventHandlers: {
        '.telemetry.batch.updated': handleRealtimeTelemetryBatch,
      },
    })
  }

  // ─── Zone status ──────────────────────────────────────────────────────────

  const variant = computed<'success' | 'neutral' | 'warning' | 'danger'>(() => {
    switch (zone.value.status) {
      case 'RUNNING': return 'success'
      case 'PAUSED': return 'neutral'
      case 'WARNING': return 'warning'
      case 'ALARM': return 'danger'
      default: return 'neutral'
    }
  })

  // ─── Action handlers ──────────────────────────────────────────────────────

  const openActionModal = (actionType: CommandType): void => {
    currentActionType.value = actionType
    modals.open('action')
  }

  const openPumpCalibrationModal = (): void => { modals.open('pumpCalibration') }

  const onRunCycle = async (): Promise<void> => {
    if (!zoneId.value) {
      logger.warn('[onRunCycle] zoneId is missing')
      showToast('Ошибка: зона не найдена', 'error', TOAST_TIMEOUT.NORMAL)
      return
    }
    router.visit(`/launch/${zoneId.value}`)
  }

  const startZoneIrrigation = async ({
    mode,
    durationSec,
  }: {
    mode: 'normal' | 'force'
    durationSec?: number
  }): Promise<void> => {
    if (!zoneId.value) return

    await api.zones.startIrrigation(zoneId.value, {
      mode,
      source: 'frontend',
      requested_duration_sec: durationSec ?? null,
    })
  }

  const onActionSubmit = async ({
    actionType,
    params,
  }: {
    actionType: CommandType
    params: Record<string, unknown>
  }): Promise<void> => {
    if (!zoneId.value) return
    setLoading('actionSubmit', true)

    const actionNames: Record<string, string> = {
      START_IRRIGATION: 'Полив',
      FORCE_IRRIGATION: 'Полив',
      FORCE_PH_CONTROL: 'Коррекция pH',
      FORCE_EC_CONTROL: 'Коррекция EC',
      FORCE_CLIMATE: 'Управление климатом',
      FORCE_LIGHTING: 'Управление освещением',
    }

    try {
      if (actionType === 'START_IRRIGATION') {
        await startZoneIrrigation({
          mode: 'normal',
          durationSec: typeof params.duration_sec === 'number' ? params.duration_sec : undefined,
        })
      } else if (actionType === 'FORCE_IRRIGATION') {
        await startZoneIrrigation({
          mode: 'force',
          durationSec: typeof params.duration_sec === 'number' ? params.duration_sec : undefined,
        })
      } else {
        await sendZoneCommand(zoneId.value, actionType, params)
      }
      const actionName = actionNames[actionType] || 'Действие'
      showToast(`${actionName} запущено успешно`, 'success', TOAST_TIMEOUT.NORMAL)
      modals.close('action')
      reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
    } catch (err) {
      logger.error(`Failed to execute ${actionType}:`, err)
      let errorMessage: string = ERROR_MESSAGES.UNKNOWN
      if (err && typeof err === 'object' && 'message' in err) errorMessage = String(err.message)
      const actionName = actionNames[actionType] || 'Действие'
      showToast(`Ошибка при выполнении "${actionName}": ${errorMessage}`, 'error', TOAST_TIMEOUT.LONG)
    } finally {
      setLoading('actionSubmit', false)
    }
  }

  const onPumpCalibrationRun = async (payload: PumpCalibrationRunPayload): Promise<void> => {
    if (!zoneId.value) return
    setLoading('pumpCalibrationRun', true)
    await pumpCalibrationActions.startPumpCalibration(payload)
    setLoading('pumpCalibrationRun', false)
  }

  const onPumpCalibrationSave = async (payload: PumpCalibrationSavePayload): Promise<void> => {
    if (!zoneId.value) return
    setLoading('pumpCalibrationSave', true)
    await pumpCalibrationActions.savePumpCalibration(payload)
    setLoading('pumpCalibrationSave', false)
  }

  const refreshZoneState = (): void => {
    if (!zoneId.value) return
    reloadZone(zoneId.value, ['zone', 'active_grow_cycle', 'active_cycle'])
    reloadZonePageProps()
  }

  const openNodeConfig = (nodeId: number, node: any): void => {
    selectedNodeId.value = nodeId
    selectedNode.value = node
    modals.open('nodeConfig')
  }

  const onNodesAttached = async (_nodeIds: number[]): Promise<void> => {
    if (!zoneId.value) return
    router.reload({ only: ['zone', 'devices'] })
  }

  // ─── Cycle actions ────────────────────────────────────────────────────────

  const {
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
  } = useZoneCycleActions({
    activeGrowCycle,
    zoneId,
    reloadZone,
    reloadZonePageProps,
    showToast,
    setLoading,
    handleError,
  })

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(async () => {
    const params = new URLSearchParams(window.location.search)

    if (params.get('start_cycle') === '1' && zoneId.value) {
      router.visit(`/launch/${zoneId.value}`)
      return
    }

    chart.initStoredRange()
    await chart.refreshChartData(chart.chartTimeRange.value)

    if (zoneId.value) {
      subscribeTelemetryRealtime(zoneId.value)
    }
  })

  onUnmounted(() => {
    if (stopTelemetryRealtimeSubscription) {
      stopTelemetryRealtimeSubscription()
      stopTelemetryRealtimeSubscription = null
    }
  })

  watch(zoneId, (newZoneId, oldZoneId) => {
    if (newZoneId === oldZoneId) {
      return
    }

    if (!newZoneId) {
      if (stopTelemetryRealtimeSubscription) {
        stopTelemetryRealtimeSubscription()
        stopTelemetryRealtimeSubscription = null
      }
      return
    }

    subscribeTelemetryRealtime(newZoneId)
  })

  /**
   * Список устройств приходит только из SSR/Inertia props; без перезагрузки он не
   * синхронизируется с БД при переключении вкладок (в отличие от телеметрии по WS).
   */
  watch(
    () => activeTab.value,
    (tab) => {
      if (tab !== 'devices' || !zoneId.value) {
        return
      }
      reloadZonePageProps(['devices'])
    },
  )

  return {
    zoneTabs,
    moreZoneTabs,
    activeTab,
    modals,
    showActionModal,
    showPumpCalibrationModal,
    showAttachNodesModal,
    showNodeConfigModal,
    currentActionType,
    selectedNodeId,
    selectedNode,
    pumpCalibrationSaveSeq,
    pumpCalibrationRunSeq,
    pumpCalibrationLastRunToken,
    loading,
    variant,
    onRunCycle,
    openActionModal,
    openPumpCalibrationModal,
    onActionSubmit,
    onPumpCalibrationRun,
    onPumpCalibrationSave,
    refreshZoneState,
    openNodeConfig,
    onNodesAttached,
    // from pageState
    ...pageState,
    // from chart
    chartTimeRange: chart.chartTimeRange,
    chartDataPh: chart.chartDataPh,
    chartDataEc: chart.chartDataEc,
    chartDataSoilMoisture: chart.chartDataSoilMoisture,
    isChartLoading: chart.isChartLoading,
    hasSoilMoisture,
    onChartTimeRangeChange: chart.onChartTimeRangeChange,
    // from cycle actions
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
  }
}
