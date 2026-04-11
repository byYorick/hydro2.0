import type { ComputedRef, Ref } from 'vue'
import { api } from '@/services/api'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastVariant } from '@/composables/useToast'
import { logger } from '@/utils/logger'
import { extractSetupWizardErrorMessage } from './setupWizardErrors'
import type {
  Greenhouse,
  GreenhouseFormState,
  SetupWizardLoadingState,
} from './setupWizardTypes'

interface SetupWizardGreenhouseCommandsOptions {
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
      const greenhouse = await api.greenhouses.create({
        ...greenhouseForm,
        uid: generatedGreenhouseUid.value,
      }) as Greenhouse
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
      const greenhouse = await api.greenhouses.getById(selectedGreenhouseId.value as number) as Greenhouse
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
