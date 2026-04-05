import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import { useCommands } from '@/composables/useCommands'
import { useTelemetry } from '@/composables/useTelemetry'
import { useZones } from '@/composables/useZones'
import { useApi } from '@/composables/useApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useModal } from '@/composables/useModal'
import { useLoading } from '@/composables/useLoading'
import { useUrlState } from '@/composables/useUrlState'
import { useToast } from '@/composables/useToast'
import { useZoneCycleActions } from '@/composables/useZoneCycleActions'
import { useZonePageState } from '@/composables/useZonePageState'
import { useZoneTelemetryChart } from '@/composables/useZoneTelemetryChart'
import { logger } from '@/utils/logger'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { ERROR_MESSAGES } from '@/constants/messages'
import { subscribeManagedChannelEvents } from '@/ws/managedChannelEvents'
import { parseNodeTelemetryBatch } from '@/ws/nodeTelemetryPayload'
import type { CommandType } from '@/types'
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

// ─── Module-level constants ───────────────────────────────────────────────────

const zoneTabs = [
  { id: 'overview', label: 'Обзор' },
  { id: 'telemetry', label: 'Телеметрия' },
  { id: 'cycle', label: 'Цикл' },
  { id: 'automation', label: 'Автоматизация' },
  { id: 'scheduler', label: 'Планировщик' },
  { id: 'events', label: 'События' },
  { id: 'alerts', label: 'Алерты' },
  { id: 'devices', label: 'Устройства' },
]

// ─── Composable ───────────────────────────────────────────────────────────────

export function useZoneShowPage() {
  const activeTab = useUrlState<string>({
    key: 'tab',
    defaultValue: zoneTabs[0].id,
    parse: (value) => {
      if (!value) return zoneTabs[0].id
      return zoneTabs.some((tab) => tab.id === value) ? value : zoneTabs[0].id
    },
    serialize: (value) => value,
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
  const showGrowthCycleModal = computed(() => modals.isModalOpen('growthCycle'))
  const showPumpCalibrationModal = computed(() => modals.isModalOpen('pumpCalibration'))
  const showAttachNodesModal = computed(() => modals.isModalOpen('attachNodes'))
  const showNodeConfigModal = computed(() => modals.isModalOpen('nodeConfig'))

  const currentActionType = ref<CommandType>('START_IRRIGATION')
  const selectedNodeId = ref<number | null>(null)
  const selectedNode = ref<any>(null)
  const growthCycleInitialData = ref<{
    recipeId?: number | null
    recipeRevisionId?: number | null
    plantId?: number | null
    startedAt?: string | null
    expectedHarvestAt?: string | null
  } | null>(null)
  const pumpCalibrationSaveSeq = ref(0)
  const pumpCalibrationRunSeq = ref(0)
  const pumpCalibrationLastRunToken = ref<string | null>(null)

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
  const { api } = useApi(showToast)
  const { subscribeToZoneCommands } = useWebSocket(showToast)
  const { handleError } = useErrorHandler(showToast)

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
      params: { from?: string; to: string }
    ) => Promise<Record<number, Array<{ ts: number; value: number }>>>,
    hasSoilMoisture,
  })

  const { zoneId, zone, activeGrowCycle, reloadZonePageProps } = pageState
  let stopTelemetryRealtimeSubscription: (() => void) | null = null

  const handleRealtimeTelemetryBatch = (payload: unknown): void => {
    const updates = parseNodeTelemetryBatch(payload)
    updates.forEach((update) => {
      pageState.applyRealtimeTelemetryPoint(update.metric_type, update.value, update.ts)
      chart.appendRealtimePoint(update.metric_type, {
        ts: update.ts,
        value: update.value,
      })
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
    modals.open('growthCycle')
  }

  const startZoneIrrigation = async ({
    mode,
    durationSec,
  }: {
    mode: 'normal' | 'force'
    durationSec?: number
  }): Promise<void> => {
    if (!zoneId.value) return

    await api.post(`/api/zones/${zoneId.value}/start-irrigation`, {
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
    try {
      const response = await api.post(`/api/zones/${zoneId.value}/calibrate-pump`, payload)
      const runToken = response?.data?.data?.run_token
      pumpCalibrationLastRunToken.value = typeof runToken === 'string' && runToken !== '' ? runToken : null
      pumpCalibrationRunSeq.value += 1
      showToast(
        'Запуск калибровки отправлен. После завершения введите фактический объём и сохраните.',
        'success',
        TOAST_TIMEOUT.NORMAL
      )
    } catch (error) {
      handleError(error, { component: 'useZoneShowPage', action: 'pumpCalibrationRun', zoneId: zoneId.value })
    } finally {
      setLoading('pumpCalibrationRun', false)
    }
  }

  const onPumpCalibrationSave = async (payload: PumpCalibrationSavePayload): Promise<void> => {
    if (!zoneId.value) return
    setLoading('pumpCalibrationSave', true)
    try {
      await api.post(`/api/zones/${zoneId.value}/calibrate-pump`, { ...payload, skip_run: true })
      reloadZone(zoneId.value, ['zone', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
      showToast('Калибровка сохранена в конфигурации канала.', 'success', TOAST_TIMEOUT.NORMAL)
      pumpCalibrationLastRunToken.value = null
      pumpCalibrationSaveSeq.value += 1
    } catch (error) {
      handleError(error, { component: 'useZoneShowPage', action: 'pumpCalibrationSave', zoneId: zoneId.value })
    } finally {
      setLoading('pumpCalibrationSave', false)
    }
  }

  const onGrowthCycleWizardSubmit = async ({
    zoneId: emittedZoneId,
  }: {
    zoneId: number
    recipeId?: number
    startedAt: string
    expectedHarvestAt?: string
  }): Promise<void> => {
    if (emittedZoneId) {
      reloadZoneAfterCommand(emittedZoneId, ['zone', 'cycles', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
    }
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
    api,
    reloadZone,
    showToast,
    setLoading,
    handleError,
  })

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(async () => {
    const params = new URLSearchParams(window.location.search)
    const parseQueryNumber = (key: string): number | null => {
      const value = params.get(key)
      if (!value) return null
      const parsed = Number(value)
      return Number.isFinite(parsed) && parsed > 0 ? parsed : null
    }

    const startedAt = params.get('started_at')
    const expectedHarvestAt = params.get('expected_harvest_at')
    growthCycleInitialData.value = {
      recipeId: parseQueryNumber('recipe_id'),
      recipeRevisionId: parseQueryNumber('recipe_revision_id'),
      plantId: parseQueryNumber('plant_id'),
      startedAt: startedAt || null,
      expectedHarvestAt: expectedHarvestAt || null,
    }

    if (params.get('start_cycle') === '1') modals.open('growthCycle')

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

  return {
    zoneTabs,
    activeTab,
    modals,
    showActionModal,
    showGrowthCycleModal,
    showPumpCalibrationModal,
    showAttachNodesModal,
    showNodeConfigModal,
    currentActionType,
    selectedNodeId,
    selectedNode,
    growthCycleInitialData,
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
    onGrowthCycleWizardSubmit,
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
