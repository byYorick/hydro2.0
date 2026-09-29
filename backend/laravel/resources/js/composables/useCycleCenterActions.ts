import { reactive } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { api } from '@/services/api'
import type { ZoneSummary } from './useCycleCenterView'

interface UseCycleCenterActionsDeps {
  showToast: (message: string, type?: 'success' | 'error' | 'warning', timeout?: number) => void
  reloadCenter: () => Promise<void>
}

export function useCycleCenterActions({
  showToast,
  reloadCenter,
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

  function setActionLoading(zoneId: number, action: string, value: boolean): void {
    actionLoading[`${zoneId}-${action}`] = value
  }

  function isActionLoading(zoneId: number, action: string): boolean {
    return Boolean(actionLoading[`${zoneId}-${action}`])
  }

  async function pauseCycle(zone: ZoneSummary): Promise<void> {
    if (!zone.cycle?.id) {
      return
    }
    setActionLoading(zone.id, 'pause', true)
    try {
      await api.growCycles.pause(zone.cycle.id)
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
      await api.growCycles.resume(zone.cycle.id)
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
      await api.growCycles.harvest(zone.cycle.id, {
        batch_label: harvestModal.batchLabel || undefined,
      })
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
      await api.growCycles.abort(zone.cycle.id, {
        notes: abortModal.notes || undefined,
      })
      showToast('Цикл остановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
      closeAbortModal()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Не удалось остановить цикл', 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      setActionLoading(zone.id, 'abort', false)
    }
  }

  return {
    actionLoading,
    harvestModal,
    abortModal,
    isActionLoading,
    pauseCycle,
    resumeCycle,
    openHarvestModal,
    closeHarvestModal,
    confirmHarvest,
    openAbortModal,
    closeAbortModal,
    confirmAbort,
  }
}
