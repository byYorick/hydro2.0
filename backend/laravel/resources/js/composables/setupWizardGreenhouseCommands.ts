import type { ComputedRef, Ref } from 'vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  Greenhouse,
  GreenhouseFormState,
  SetupWizardLoadingState,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient } from './setupWizardDataLoaders'

interface SetupWizardGreenhouseCommandsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  generatedGreenhouseUid: ComputedRef<string>
  selectedGreenhouseId: Ref<number | null>
  selectedGreenhouse: Ref<Greenhouse | null>
  greenhouseForm: GreenhouseFormState
  loaders: {
    loadGreenhouses: () => Promise<void>
    loadZones: (greenhouseId?: number) => Promise<void>
  }
}

export interface SetupWizardGreenhouseCommandActions {
  createGreenhouse: () => Promise<void>
  selectGreenhouse: () => Promise<void>
}

export function canCreateGreenhouse(canConfigure: boolean, greenhouseName: string): boolean {
  return canConfigure && greenhouseName.trim().length > 0
}

export function canSelectGreenhouse(canConfigure: boolean, selectedGreenhouseId: number | null): boolean {
  return canConfigure && selectedGreenhouseId !== null
}

export function createSetupWizardGreenhouseCommands(
  options: SetupWizardGreenhouseCommandsOptions
): SetupWizardGreenhouseCommandActions {
  const {
    api,
    loading,
    canConfigure,
    showToast,
    generatedGreenhouseUid,
    selectedGreenhouseId,
    selectedGreenhouse,
    greenhouseForm,
    loaders,
  } = options

  async function createGreenhouse(): Promise<void> {
    if (!canCreateGreenhouse(canConfigure.value, greenhouseForm.name)) {
      return
    }

    loading.stepGreenhouse = true
    try {
      const response = await api.post('/greenhouses', {
        ...greenhouseForm,
        uid: generatedGreenhouseUid.value,
      })

      const greenhouse = extractData<Greenhouse>(response.data)
      if (!greenhouse?.id) {
        throw new Error('Greenhouse not returned from API')
      }

      selectedGreenhouse.value = greenhouse
      selectedGreenhouseId.value = greenhouse.id
      showToast('Теплица создана', 'success', TOAST_TIMEOUT.NORMAL)

      await loaders.loadGreenhouses()
      await loaders.loadZones(greenhouse.id)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to create greenhouse', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось создать теплицу'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepGreenhouse = false
    }
  }

  async function selectGreenhouse(): Promise<void> {
    if (!canSelectGreenhouse(canConfigure.value, selectedGreenhouseId.value)) {
      return
    }

    loading.stepGreenhouse = true
    try {
      const response = await api.get(`/greenhouses/${selectedGreenhouseId.value}`)
      const greenhouse = extractData<Greenhouse>(response.data)
      if (!greenhouse?.id) {
        throw new Error('Greenhouse not found')
      }

      selectedGreenhouse.value = greenhouse
      showToast('Теплица выбрана', 'success', TOAST_TIMEOUT.NORMAL)
      await loaders.loadZones(greenhouse.id)
    } catch (error) {
      logger.error('[Setup/Wizard] Failed to select greenhouse', { error })
      showToast(extractSetupWizardErrorMessage(error, 'Не удалось выбрать теплицу'), 'error', TOAST_TIMEOUT.NORMAL)
    } finally {
      loading.stepGreenhouse = false
    }
  }

  return {
    createGreenhouse,
    selectGreenhouse,
  }
}
