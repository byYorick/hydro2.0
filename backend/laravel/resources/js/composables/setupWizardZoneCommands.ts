import type { ComputedRef, Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  SetupWizardLoadingState,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient } from './setupWizardDataLoaders'

interface SetupWizardZoneCommandsOptions {
  api: SetupWizardDataApiClient
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
    api,
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

      const response = await api.post('/zones', {
        name: zoneForm.name,
        description: zoneForm.description,
        greenhouse_id: greenhouseId,
      })

      const zone = extractData<Zone>(response.data)
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
      const response = await api.get(`/zones/${selectedZoneId.value}`)
      const zone = extractData<Zone>(response.data)
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
