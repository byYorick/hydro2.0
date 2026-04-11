import type { ComputedRef, Ref } from 'vue'
import { api } from '@/services/api'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  SetupWizardLoadingState,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'

interface SetupWizardZoneCommandsOptions {
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  selectedGreenhouse: Ref<{ id: number } | null>
  selectedZoneId: Ref<number | null>
  selectedZone: Ref<Zone | null>
  zoneForm: ZoneFormState
  loaders: {
    loadZones: (greenhouseId?: number) => Promise<void>
  }
}

export interface SetupWizardZoneCommandActions {
  createZone: () => Promise<void>
  selectZone: () => Promise<void>
}

export function canCreateZone(canConfigure: boolean, greenhouseId: number | null | undefined, zoneName: string): boolean {
  return canConfigure && Boolean(greenhouseId) && zoneName.trim().length > 0
}

export function canSelectZone(canConfigure: boolean, selectedZoneId: number | null): boolean {
  return canConfigure && selectedZoneId !== null
}

export function createSetupWizardZoneCommands(
  options: SetupWizardZoneCommandsOptions
): SetupWizardZoneCommandActions {
  const {
    loading,
    canConfigure,
    showToast,
    selectedGreenhouse,
    selectedZoneId,
    selectedZone,
    zoneForm,
    loaders,
  } = options

  async function createZone(): Promise<void> {
    if (!canCreateZone(canConfigure.value, selectedGreenhouse.value?.id, zoneForm.name)) {
      return
    }

    loading.stepZone = true
    try {
      const greenhouseId = selectedGreenhouse.value?.id
      if (!greenhouseId) {
        return
      }

      const zone = await api.zones.create({
        name: zoneForm.name,
        description: zoneForm.description,
        greenhouse_id: greenhouseId,
      }) as Zone
      if (!zone?.id) {
        throw new Error('Zone not returned from API')
      }

      selectedZone.value = zone
      selectedZoneId.value = zone.id
      showToast('Зона создана', 'success', TOAST_TIMEOUT.NORMAL)

      await loaders.loadZones(greenhouseId)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to create zone', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось создать зону'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepZone = false
    }
  }

  async function selectZone(): Promise<void> {
    if (!canSelectZone(canConfigure.value, selectedZoneId.value)) {
      return
    }

    loading.stepZone = true
    try {
      const zone = await api.zones.getById(selectedZoneId.value as number) as Zone
      if (!zone?.id) {
        throw new Error('Zone not found')
      }

      selectedZone.value = zone
      showToast('Зона выбрана', 'success', TOAST_TIMEOUT.NORMAL)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to select zone', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось выбрать зону'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepZone = false
    }
  }

  return {
    createZone,
    selectZone,
  }
}
