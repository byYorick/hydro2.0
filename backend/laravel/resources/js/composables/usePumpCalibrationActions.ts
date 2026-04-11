import { ref } from 'vue'
import { api } from '@/services/api'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'

type ToastVariant = 'success' | 'error' | 'warning' | 'info'

interface UsePumpCalibrationActionsOptions {
  getZoneId: () => number | null
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  onRunSuccess?: () => Promise<void> | void
  onSaveSuccess?: () => Promise<void> | void
  onRunError?: (error: unknown) => Promise<void> | void
  onSaveError?: (error: unknown) => Promise<void> | void
  runSuccessMessage?: string
  runErrorMessage?: string
  saveSuccessMessage?: string
  saveErrorMessage?: string
  successTimeout?: number
  errorTimeout?: number
}

export function usePumpCalibrationActions(options: UsePumpCalibrationActionsOptions) {
  const loadingRun = ref(false)
  const loadingSave = ref(false)
  const saveSeq = ref(0)
  const runSeq = ref(0)
  const lastRunToken = ref<string | null>(null)

  async function startPumpCalibration(payload: PumpCalibrationRunPayload): Promise<boolean> {
    const zoneId = options.getZoneId()
    if (!zoneId) {
      return false
    }

    loadingRun.value = true
    try {
      const response = await api.zones.calibratePump(zoneId, payload)
      const runToken = response?.run_token
      lastRunToken.value = typeof runToken === 'string' && runToken !== '' ? runToken : null
      runSeq.value += 1
      await options.onRunSuccess?.()
      options.showToast(
        options.runSuccessMessage ?? 'Запуск калибровки отправлен.',
        'success',
        options.successTimeout
      )
      return true
    } catch (error) {
      if (options.onRunError) {
        await options.onRunError(error)
      } else {
        options.showToast(
          options.runErrorMessage ?? 'Не удалось запустить калибровку насоса.',
          'error',
          options.errorTimeout
        )
      }
      return false
    } finally {
      loadingRun.value = false
    }
  }

  async function savePumpCalibration(payload: PumpCalibrationSavePayload): Promise<boolean> {
    const zoneId = options.getZoneId()
    if (!zoneId) {
      return false
    }

    loadingSave.value = true
    try {
      await api.zones.calibratePump(zoneId, { ...payload, skip_run: true })
      lastRunToken.value = null
      saveSeq.value += 1
      await options.onSaveSuccess?.()
      options.showToast(
        options.saveSuccessMessage ?? 'Калибровка насоса сохранена.',
        'success',
        options.successTimeout
      )
      return true
    } catch (error) {
      if (options.onSaveError) {
        await options.onSaveError(error)
      } else {
        options.showToast(
          options.saveErrorMessage ?? 'Не удалось сохранить калибровку насоса.',
          'error',
          options.errorTimeout
        )
      }
      return false
    } finally {
      loadingSave.value = false
    }
  }

  return {
    loadingRun,
    loadingSave,
    saveSeq,
    runSeq,
    lastRunToken,
    startPumpCalibration,
    savePumpCalibration,
  }
}
