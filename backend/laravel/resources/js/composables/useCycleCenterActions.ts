import { reactive } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ZoneSummary } from './useCycleCenterView'

type ZoneActionType = 'FORCE_IRRIGATION'

interface ApiLike {
  post: (url: string, payload?: Record<string, unknown>) => Promise<{ data?: { status?: string } }>
}

interface UseCycleCenterActionsDeps {
  api: ApiLike
  showToast: (message: string, type?: 'success' | 'error' | 'warning', timeout?: number) => void
  reloadCenter: () => Promise<void>
  sendZoneCommand: (zoneId: number, actionType: ZoneActionType, params: Record<string, number>) => Promise<unknown>
}

export function useCycleCenterActions({
  api,
  showToast,
  reloadCenter,
  sendZoneCommand,
}: UseCycleCenterActionsDeps) {
  const actionLoading = reactive<Record<string, boolean>>({})

  const harvestModal = reactive<{ open: boolean; zone: ZoneSummary | null; batchLabel: string }>({
    open: false,
    zone: null,
    batchLabel: '',
  })

  const abortModal = reactive<{ open: boolean; zone: ZoneSummary | null; notes: string }>({
    open: false,
    zone: null,
    notes: '',
  })

  const actionModal = reactive<{ open: boolean; zone: ZoneSummary | null; actionType: ZoneActionType }>({
    open: false,
    zone: null,
    actionType: 'FORCE_IRRIGATION',
  })

  function setActionLoading(zoneId: number, action: string, value: boolean): void {
    actionLoading[`${zoneId}-${action}`] = value
  }

  function isActionLoading(zoneId: number, action: string): boolean {
    return Boolean(actionLoading[`${zoneId}-${action}`])
  }

  function ensureOkStatus(response: { data?: { status?: string } }, errorMessage: string): void {
    if (response.data?.status !== 'ok') {
      throw new Error(errorMessage)
    }
  }

  async function pauseCycle(zone: ZoneSummary): Promise<void> {
    if (!zone.cycle?.id) {
      return
    }
    setActionLoading(zone.id, 'pause', true)
    try {
      const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/pause`)
      ensureOkStatus(response, 'Не удалось приостановить цикл')
      showToast('Цикл приостановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось приостановить цикл', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      setActionLoading(zone.id, 'pause', false)
    }
  }

  async function resumeCycle(zone: ZoneSummary): Promise<void> {
    if (!zone.cycle?.id) {
      return
    }
    setActionLoading(zone.id, 'resume', true)
    try {
      const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/resume`)
      ensureOkStatus(response, 'Не удалось возобновить цикл')
      showToast('Цикл возобновлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось возобновить цикл', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      setActionLoading(zone.id, 'resume', false)
    }
  }

  function openHarvestModal(zone: ZoneSummary): void {
    harvestModal.zone = zone
    harvestModal.batchLabel = ''
    harvestModal.open = true
  }

  function closeHarvestModal(): void {
    harvestModal.open = false
    harvestModal.zone = null
  }

  async function confirmHarvest(): Promise<void> {
    const zone = harvestModal.zone
    if (!zone?.cycle?.id) {
      return
    }
    setActionLoading(zone.id, 'harvest', true)
    try {
      const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/harvest`, {
        batch_label: harvestModal.batchLabel || undefined,
      })
      ensureOkStatus(response, 'Не удалось зафиксировать урожай')
      showToast('Урожай зафиксирован', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
      closeHarvestModal()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось зафиксировать урожай', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      setActionLoading(zone.id, 'harvest', false)
    }
  }

  function openAbortModal(zone: ZoneSummary): void {
    abortModal.zone = zone
    abortModal.notes = ''
    abortModal.open = true
  }

  function closeAbortModal(): void {
    abortModal.open = false
    abortModal.zone = null
  }

  async function confirmAbort(): Promise<void> {
    const zone = abortModal.zone
    if (!zone?.cycle?.id) {
      return
    }
    setActionLoading(zone.id, 'abort', true)
    try {
      const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/abort`, {
        notes: abortModal.notes || undefined,
      })
      ensureOkStatus(response, 'Не удалось остановить цикл')
      showToast('Цикл остановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
      closeAbortModal()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось остановить цикл', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      setActionLoading(zone.id, 'abort', false)
    }
  }

  function openActionModal(zone: ZoneSummary, actionType: ZoneActionType): void {
    actionModal.open = true
    actionModal.zone = zone
    actionModal.actionType = actionType
  }

  function closeActionModal(): void {
    actionModal.open = false
    actionModal.zone = null
  }

  async function submitAction(payload: { actionType: ZoneActionType; params: Record<string, number> }): Promise<void> {
    if (!actionModal.zone) {
      return
    }
    await sendZoneCommand(actionModal.zone.id, payload.actionType, payload.params)
    closeActionModal()
  }

  return {
    actionLoading,
    harvestModal,
    abortModal,
    actionModal,
    isActionLoading,
    pauseCycle,
    resumeCycle,
    openHarvestModal,
    closeHarvestModal,
    confirmHarvest,
    openAbortModal,
    closeAbortModal,
    confirmAbort,
    openActionModal,
    closeActionModal,
    submitAction,
  }
}
