import type { ComputedRef, Ref } from 'vue'
import type { ToastVariant } from '@/composables/useToast'
import type {
  Greenhouse,
  GreenhouseFormState,
  SetupWizardLoadingState,
  Zone,
  ZoneFormState,
} from './setupWizardTypes'
import type { SetupWizardDataApiClient } from './setupWizardDataLoaders'
import {
  createSetupWizardGreenhouseCommands,
  type SetupWizardGreenhouseCommandActions,
} from './setupWizardGreenhouseCommands'
import {
  createSetupWizardZoneCommands,
  type SetupWizardZoneCommandActions,
} from './setupWizardZoneCommands'

interface SetupWizardGreenhouseZoneCommandsOptions {
  api: SetupWizardDataApiClient
  loading: SetupWizardLoadingState
  canConfigure: ComputedRef<boolean>
  showToast: (message: string, variant: ToastVariant, timeout?: number) => void
  generatedGreenhouseUid: ComputedRef<string>
  selectedGreenhouseId: Ref<number | null>
  selectedZoneId: Ref<number | null>
  selectedGreenhouse: Ref<Greenhouse | null>
  selectedZone: Ref<Zone | null>
  greenhouseForm: GreenhouseFormState
  zoneForm: ZoneFormState
  loaders: {
    loadGreenhouses: () => Promise<void>
    loadZones: (greenhouseId?: number) => Promise<void>
  }
}

export type SetupWizardGreenhouseZoneCommandActions = SetupWizardGreenhouseCommandActions & SetupWizardZoneCommandActions

export function createSetupWizardGreenhouseZoneCommands(
  options: SetupWizardGreenhouseZoneCommandsOptions
): SetupWizardGreenhouseZoneCommandActions {
  const greenhouseCommands = createSetupWizardGreenhouseCommands({
    api: options.api,
    loading: options.loading,
    canConfigure: options.canConfigure,
    showToast: options.showToast,
    generatedGreenhouseUid: options.generatedGreenhouseUid,
    selectedGreenhouseId: options.selectedGreenhouseId,
    selectedGreenhouse: options.selectedGreenhouse,
    greenhouseForm: options.greenhouseForm,
    loaders: {
      loadGreenhouses: options.loaders.loadGreenhouses,
      loadZones: options.loaders.loadZones,
    },
  })

  const zoneCommands = createSetupWizardZoneCommands({
    api: options.api,
    loading: options.loading,
    canConfigure: options.canConfigure,
    showToast: options.showToast,
    selectedGreenhouse: options.selectedGreenhouse,
    selectedZoneId: options.selectedZoneId,
    selectedZone: options.selectedZone,
    zoneForm: options.zoneForm,
    loaders: {
      loadZones: options.loaders.loadZones,
    },
  })

  return {
    ...greenhouseCommands,
    ...zoneCommands,
  }
}
